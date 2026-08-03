from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.config import Settings, get_settings
from kelbet.payments import payment_product_row, seed_payment_products

BOT_TOKEN = "999:TEST-TOKEN-PAYMENTS"


def _signed_init_data(telegram_id: int = 930_001) -> str:
    user = json.dumps(
        {
            "id": telegram_id,
            "username": "payment_api_user",
            "language_code": "ru",
            "first_name": "Pay",
        },
        separators=(",", ":"),
    )
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": user,
            "query_id": f"pay-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def payment_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_TERMS_URL", "https://kelbet.ai/terms")
    monkeypatch.setenv("PAYMENT_TERMS_VERSION", "test-v1")
    monkeypatch.setenv("PAYMENT_REFUND_POLICY_URL", "https://kelbet.ai/refunds")
    monkeypatch.setenv("PAYMENT_SELLER_IDENTITY", "KELBET TEST SELLER")
    monkeypatch.setenv("PAYMENT_FINANCE_REVIEW_CONFIRMED", "true")
    monkeypatch.setenv("SUPPORT_USERNAME", "kelbet_support")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
async def payment_api_client(
    session_factory: async_sessionmaker[AsyncSession],
    payment_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    async with session_factory() as session, session.begin():
        await seed_payment_products(session)
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
async def test_products_create_invoice_and_history(
    payment_api_client: AsyncClient,
) -> None:
    token = await _login(payment_api_client)
    headers = {"Authorization": f"Bearer {token}"}

    products = await payment_api_client.get("/api/v1/payments/products", headers=headers)
    assert products.status_code == 200
    assert products.json()["payments_enabled"] is True
    assert products.json()["items"][0]["slug"] == "starter"

    rejected = await payment_api_client.post(
        "/api/v1/payments/orders",
        headers={**headers, "Idempotency-Key": "api-pay-rejected"},
        json={"product_slug": "starter", "terms_accepted": False},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "payment_validation_error"

    created = await payment_api_client.post(
        "/api/v1/payments/orders",
        headers={**headers, "Idempotency-Key": "api-pay-1"},
        json={"product_slug": "starter", "terms_accepted": True},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    starter = payment_product_row("starter")
    assert body["currency"] == "XTR"
    assert body["total_amount"] == starter["stars"]
    assert body["credits"] == starter["credits"]
    assert body["invoice_url"].startswith("https://t.me/$kelbet_")

    replay = await payment_api_client.post(
        "/api/v1/payments/orders",
        headers={**headers, "Idempotency-Key": "api-pay-1"},
        json={"product_slug": "starter", "terms_accepted": True},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == body["id"]

    history = await payment_api_client.get("/api/v1/payments/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["id"] == body["id"]
