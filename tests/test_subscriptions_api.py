"""Mini-app subscription endpoints.

The point being checked is that the API can offer, start and cancel a subscription without
ever granting credits itself. Only a Telegram charge delivered to the bot does that, so an
endpoint that quietly topped up a wallet would be a way to get credits for free.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.config import Settings, get_settings
from kelbet.db.models import Subscription, SubscriptionPeriod, Wallet
from kelbet.domain.enums import Plan, SubscriptionStatus
from kelbet.repositories.user import UserRepository
from kelbet.services.subscription import SubscriptionService
from kelbet.subscriptions import seed_subscription_plans, subscription_plan_row

BOT_TOKEN = "999:TEST-TOKEN-SUBSCRIPTIONS"
TELEGRAM_ID = 950_001


def _signed_init_data(telegram_id: int = TELEGRAM_ID) -> str:
    user = json.dumps(
        {
            "id": telegram_id,
            "username": "sub_api_user",
            "language_code": "ru",
            "first_name": "Sub",
        },
        separators=(",", ":"),
    )
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": user,
            "query_id": f"sub-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def subscription_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_TERMS_URL", "https://kelbet.ai/terms")
    monkeypatch.setenv("PAYMENT_TERMS_VERSION", "test-v1")
    monkeypatch.setenv("PAYMENT_REFUND_POLICY_URL", "https://kelbet.ai/refunds")
    monkeypatch.setenv("PAYMENT_SELLER_IDENTITY", "KELBET TEST SELLER")
    monkeypatch.setenv("PAYMENT_FINANCE_REVIEW_CONFIRMED", "true")
    monkeypatch.setenv("SUPPORT_USERNAME", "kelbet_support")
    monkeypatch.setenv("WELCOME_CREDITS", "60")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
async def subscription_api_client(
    session_factory: async_sessionmaker[AsyncSession],
    subscription_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _login(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed_init_data()},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_plans_endpoint_lists_tiers_and_no_current_subscription(
    subscription_api_client: AsyncClient,
) -> None:
    token = await _login(subscription_api_client)
    response = await subscription_api_client.get(
        "/api/v1/subscriptions/plans",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subscriptions_enabled"] is True
    assert body["current"] is None
    # Telegram bills a fixed 30-day period, so the client never has to infer it.
    assert body["period_days"] == 30
    assert [item["slug"] for item in body["items"]] == ["start", "pro", "studio", "business"]
    pro = next(item for item in body["items"] if item["slug"] == "pro")
    seeded = subscription_plan_row("pro")
    assert pro["stars"] == seeded["stars"]
    assert pro["monthly_credits"] == seeded["monthly_credits"]
    assert pro["kzt_price"] == seeded["kzt_price"]
    assert pro["name"] == seeded["localization"]["ru"]["name"]


@pytest.mark.asyncio
async def test_checkout_returns_a_link_and_grants_nothing(
    subscription_api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    token = await _login(subscription_api_client)
    response = await subscription_api_client.post(
        "/api/v1/subscriptions/checkout",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "api-sub-1"},
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["invoice_url"].startswith("https://t.me/$kelbet_sub_")
    assert body["period_days"] == 30
    assert body["stars"] == subscription_plan_row("pro")["stars"]

    async with session_factory() as session:
        # A checkout is an intent, not a payment: no period, no credits, still free.
        assert await session.scalar(select(func.count()).select_from(SubscriptionPeriod)) == 0
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 60
        user = await UserRepository(session).get_by_telegram_id(TELEGRAM_ID)
        assert user is not None and user.plan == Plan.FREE.value


@pytest.mark.asyncio
async def test_repeated_checkout_reuses_the_pending_subscription(
    subscription_api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A retried request — a double tap, or a client retry after a timeout — must not create
    a second subscription the user would be billed for separately."""
    token = await _login(subscription_api_client)
    headers = {"Authorization": f"Bearer {token}"}
    first = await subscription_api_client.post(
        "/api/v1/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "api-sub-retry-1"},
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
    )
    second = await subscription_api_client.post(
        "/api/v1/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "api-sub-retry-2"},
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["subscription_id"] == second.json()["subscription_id"]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Subscription)) == 1


@pytest.mark.asyncio
async def test_checkout_rejects_unaccepted_and_stale_terms(
    subscription_api_client: AsyncClient,
) -> None:
    token = await _login(subscription_api_client)
    headers = {"Authorization": f"Bearer {token}"}
    unaccepted = await subscription_api_client.post(
        "/api/v1/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "api-sub-terms-1"},
        json={"plan_slug": "pro", "terms_accepted": False, "terms_version": "test-v1"},
    )
    stale = await subscription_api_client.post(
        "/api/v1/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "api-sub-terms-2"},
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "old-version"},
    )
    unknown_plan = await subscription_api_client.post(
        "/api/v1/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "api-sub-terms-3"},
        json={"plan_slug": "enterprise", "terms_accepted": True, "terms_version": "test-v1"},
    )

    assert unaccepted.status_code == 422
    assert stale.status_code == 422
    assert unknown_plan.status_code == 422


@pytest.mark.asyncio
async def test_cancel_reports_access_until_the_end_of_the_paid_period(
    subscription_api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    subscription_settings: Settings,
) -> None:
    token = await _login(subscription_api_client)
    created = await subscription_api_client.post(
        "/api/v1/subscriptions/checkout",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "api-sub-cancel"},
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
    )
    assert created.status_code == 200

    # Simulate the charge Telegram would deliver to the bot; the API has no way to do this.
    expires = (datetime.now(UTC) + timedelta(days=30)).replace(microsecond=0)
    pro = subscription_plan_row("pro")
    async with session_factory() as session, session.begin():
        subscription = (await session.execute(select(Subscription))).scalar_one()
        result = await SubscriptionService(session, subscription_settings).apply_successful_payment(
            telegram_id=TELEGRAM_ID,
            invoice_payload=subscription.invoice_payload,
            currency="XTR",
            total_amount=int(pro["stars"]),
            telegram_payment_charge_id="api-sub-charge",
            provider_payment_charge_id=None,
            subscription_expiration_date=expires,
            is_first_recurring=True,
        )
        assert result.applied is True

    plans = await subscription_api_client.get(
        "/api/v1/subscriptions/plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    current = plans.json()["current"]
    assert current is not None
    assert current["status"] == SubscriptionStatus.ACTIVE.value
    assert current["plan"] == Plan.PRO.value
    assert current["cancel_at_period_end"] is False

    cancelled = await subscription_api_client.post(
        "/api/v1/subscriptions/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancel_at_period_end"] is True
    assert cancelled.json()["access_until"] == expires.isoformat()
    async with session_factory() as session:
        user = await UserRepository(session).get_by_telegram_id(TELEGRAM_ID)
        # Paid for, therefore still entitled. Only the expiry worker takes the tier away.
        assert user is not None and user.plan == Plan.PRO.value


@pytest.mark.asyncio
async def test_cancel_without_a_subscription_is_rejected(
    subscription_api_client: AsyncClient,
) -> None:
    token = await _login(subscription_api_client)
    response = await subscription_api_client.post(
        "/api/v1/subscriptions/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_plans_are_hidden_when_the_feature_is_off(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the flag off the endpoint must still answer, but offer nothing — a client that
    renders whatever it receives should show no tiers rather than break."""
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("SUBSCRIPTIONS_ENABLED", "false")
    monkeypatch.setenv("PAYMENT_TERMS_URL", "https://kelbet.ai/terms")
    monkeypatch.setenv("PAYMENT_TERMS_VERSION", "test-v1")
    monkeypatch.setenv("PAYMENT_REFUND_POLICY_URL", "https://kelbet.ai/refunds")
    monkeypatch.setenv("PAYMENT_SELLER_IDENTITY", "KELBET TEST SELLER")
    monkeypatch.setenv("PAYMENT_FINANCE_REVIEW_CONFIRMED", "true")
    monkeypatch.setenv("SUPPORT_USERNAME", "kelbet_support")
    get_settings.cache_clear()
    try:
        async with session_factory() as session, session.begin():
            await seed_subscription_plans(session)
        app = create_app(testing=True)
        app.state.session_factory = session_factory
        app.state.replay_store = MemoryReplayStore()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            plans = await client.get(
                "/api/v1/subscriptions/plans",
                headers={"Authorization": f"Bearer {token}"},
            )
            checkout = await client.post(
                "/api/v1/subscriptions/checkout",
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "api-sub-off"},
                json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
            )
    finally:
        get_settings.cache_clear()

    assert plans.status_code == 200
    assert plans.json()["items"] == []
    assert plans.json()["subscriptions_enabled"] is False
    # The flag being off is a service-level condition, not a bad request from the client.
    assert checkout.status_code == 503
    assert checkout.json()["error"]["code"] == "payments_unavailable"
