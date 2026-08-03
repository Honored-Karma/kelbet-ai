"""Mini-app subscription endpoints.

What is being checked is that the API can offer, start and cancel a subscription without
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
from kelbet.db.models import SubscriptionGrant, UserSubscription, Wallet
from kelbet.domain.enums import Plan, SubscriptionStatus
from kelbet.repositories.user import UserRepository
from kelbet.services.subscription import SubscriptionService
from kelbet.subscriptions import seed_subscription_plans
from kelbet.subscriptions.seeds import subscription_plan_rows

BOT_TOKEN = "999:TEST-TOKEN-SUBSCRIPTIONS"
TELEGRAM_ID = 970_001
PRO = next(row for row in subscription_plan_rows() if row["slug"] == "pro")


def _signed_init_data() -> str:
    user = json.dumps(
        {
            "id": TELEGRAM_ID,
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
            "query_id": f"sub-{TELEGRAM_ID}",
        },
        BOT_TOKEN,
    )


def _env(monkeypatch: pytest.MonkeyPatch, *, subscriptions: str) -> None:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("SUBSCRIPTIONS_ENABLED", subscriptions)
    monkeypatch.setenv("PAYMENT_TERMS_URL", "https://kelbet.ai/terms")
    monkeypatch.setenv("PAYMENT_TERMS_VERSION", "test-v1")
    monkeypatch.setenv("PAYMENT_REFUND_POLICY_URL", "https://kelbet.ai/refunds")
    monkeypatch.setenv("PAYMENT_SELLER_IDENTITY", "KELBET TEST SELLER")
    monkeypatch.setenv("PAYMENT_FINANCE_REVIEW_CONFIRMED", "true")
    monkeypatch.setenv("SUPPORT_USERNAME", "kelbet_support")
    monkeypatch.setenv("WELCOME_CREDITS", "60")


@pytest.fixture
def subscription_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    _env(monkeypatch, subscriptions="true")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
async def api(
    session_factory: async_sessionmaker[AsyncSession],
    subscription_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _login(client: AsyncClient) -> str:
    response = await client.post("/api/v1/auth/telegram", json={"init_data": _signed_init_data()})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_plans_lists_tiers_and_reports_no_current_subscription(api: AsyncClient) -> None:
    token = await _login(api)
    response = await api.get(
        "/api/v1/subscriptions/plans", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subscriptions_enabled"] is True
    assert body["current"] is None
    assert [item["slug"] for item in body["items"]] == ["start", "pro", "studio", "business"]
    pro = next(item for item in body["items"] if item["slug"] == "pro")
    assert pro["stars"] == PRO["stars"]
    assert pro["credits_per_period"] == PRO["credits_per_period"]
    assert pro["price_kzt"] == PRO["price_kzt"]
    assert pro["referral_percent"] == PRO["referral_percent"]
    # Telegram bills a fixed 30-day period, so the client never has to infer it.
    assert pro["period_days"] == 30
    assert pro["name"] == PRO["localization"]["ru"]["name"]


@pytest.mark.asyncio
async def test_checkout_returns_a_link_and_grants_nothing(
    api: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    token = await _login(api)
    response = await api.post(
        "/api/v1/subscriptions/checkout",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["invoice_url"].startswith("https://t.me/$kelbet_sub_")
    assert body["stars"] == PRO["stars"]
    assert body["period_days"] == 30

    async with session_factory() as session:
        # A checkout is an intent, not a payment.
        assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == 0
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 60
        user = await UserRepository(session).get_by_telegram_id(TELEGRAM_ID)
        assert user is not None and user.plan == Plan.FREE.value


@pytest.mark.asyncio
async def test_retried_checkout_does_not_create_a_second_subscription(
    api: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A double tap or a client retry after a timeout must not produce two billable links."""
    token = await _login(api)
    headers = {"Authorization": f"Bearer {token}"}
    body = {"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"}
    first = await api.post("/api/v1/subscriptions/checkout", headers=headers, json=body)
    second = await api.post("/api/v1/subscriptions/checkout", headers=headers, json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["subscription_id"] == second.json()["subscription_id"]
    assert first.json()["invoice_url"] == second.json()["invoice_url"]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(UserSubscription)) == 1


@pytest.mark.asyncio
async def test_checkout_rejects_unaccepted_and_stale_terms(api: AsyncClient) -> None:
    token = await _login(api)
    headers = {"Authorization": f"Bearer {token}"}
    unaccepted = await api.post(
        "/api/v1/subscriptions/checkout",
        headers=headers,
        json={"plan_slug": "pro", "terms_accepted": False, "terms_version": "test-v1"},
    )
    stale = await api.post(
        "/api/v1/subscriptions/checkout",
        headers=headers,
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "ancient"},
    )
    unknown = await api.post(
        "/api/v1/subscriptions/checkout",
        headers=headers,
        json={"plan_slug": "enterprise", "terms_accepted": True, "terms_version": "test-v1"},
    )

    assert unaccepted.status_code >= 400
    assert stale.status_code >= 400
    assert unknown.status_code >= 400


@pytest.mark.asyncio
async def test_cancel_reports_access_until_the_paid_period_ends(
    api: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    subscription_settings: Settings,
) -> None:
    token = await _login(api)
    created = await api.post(
        "/api/v1/subscriptions/checkout",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
    )
    assert created.status_code == 200

    # Simulate the charge Telegram delivers to the bot; the API has no way to do this.
    expires = (datetime.now(UTC) + timedelta(days=30)).replace(microsecond=0)
    async with session_factory() as session, session.begin():
        subscription = (await session.execute(select(UserSubscription))).scalar_one()
        assert subscription.invoice_payload is not None
        outcome = await SubscriptionService(session, subscription_settings).apply_charge(
            telegram_id=TELEGRAM_ID,
            invoice_payload=subscription.invoice_payload,
            currency="XTR",
            total_amount=int(PRO["stars"]),
            charge_id="api-charge-1",
            expires_at=expires,
        )
        assert outcome.applied is True

    plans = await api.get(
        "/api/v1/subscriptions/plans", headers={"Authorization": f"Bearer {token}"}
    )
    current = plans.json()["current"]
    assert current is not None
    assert current["status"] == SubscriptionStatus.ACTIVE.value
    assert current["cancel_at_period_end"] is False
    assert current["renewal_failed"] is False

    cancelled = await api.post(
        "/api/v1/subscriptions/cancel", headers={"Authorization": f"Bearer {token}"}
    )

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancel_at_period_end"] is True
    assert cancelled.json()["access_until"] == expires.isoformat()
    async with session_factory() as session:
        user = await UserRepository(session).get_by_telegram_id(TELEGRAM_ID)
        # Paid for, therefore still entitled. Only the expiry sweep takes the tier away.
        assert user is not None and user.plan == Plan.PRO.value


@pytest.mark.asyncio
async def test_cancel_without_a_subscription_is_rejected(api: AsyncClient) -> None:
    token = await _login(api)
    response = await api.post(
        "/api/v1/subscriptions/cancel", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code >= 400


@pytest.mark.asyncio
async def test_plans_offer_nothing_when_the_feature_is_off(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the flag off the endpoint must still answer, but offer nothing — a client that
    renders whatever it receives should show no tiers rather than break."""
    _env(monkeypatch, subscriptions="false")
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
                "/api/v1/subscriptions/plans", headers={"Authorization": f"Bearer {token}"}
            )
            checkout = await client.post(
                "/api/v1/subscriptions/checkout",
                headers={"Authorization": f"Bearer {token}"},
                json={"plan_slug": "pro", "terms_accepted": True, "terms_version": "test-v1"},
            )
    finally:
        get_settings.cache_clear()

    assert plans.status_code == 200
    assert plans.json()["items"] == []
    assert plans.json()["subscriptions_enabled"] is False
    # The flag being off is a service condition, not a bad request from the client.
    assert checkout.status_code == 503
    assert checkout.json()["error"]["code"] == "payments_unavailable"
