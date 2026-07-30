"""Rate limit dependency tests for auth + generations."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.rate_limit import MemoryRateLimiter

BOT_TOKEN = "999:TEST-TOKEN-RL"


def _signed(*, telegram_id: int) -> str:
    user = json.dumps(
        {"id": telegram_id, "username": f"rl_{telegram_id}", "language_code": "ru"},
        separators=(",", ":"),
    )
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": user,
            "query_id": f"q-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def rl_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "3")
    monkeypatch.setenv("RATE_LIMIT_GENERATIONS_PER_MINUTE", "2")
    monkeypatch.setenv("WELCOME_CREDITS", "50")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    rl_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)

    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    app.state.rate_limiter = MemoryRateLimiter()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_auth_rate_limit_returns_429(api_client: AsyncClient) -> None:
    for index in range(3):
        response = await api_client.post(
            "/api/v1/auth/telegram",
            json={"init_data": _signed(telegram_id=930000 + index)},
        )
        assert response.status_code == 200, response.text

    blocked = await api_client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed(telegram_id=930099)},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.headers.get("retry-after") == "60"


@pytest.mark.asyncio
async def test_generation_rate_limit_returns_429(api_client: AsyncClient) -> None:
    auth = await api_client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed(telegram_id=930200)},
    )
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    quote_ids: list[str] = []
    for _ in range(2):
        quote = await api_client.post(
            "/api/v1/wallet/quote",
            headers=headers,
            json={"model_slug": "mock-text", "params": {}},
        )
        assert quote.status_code == 200, quote.text
        quote_ids.append(quote.json()["quote_id"])

    for index, quote_id in enumerate(quote_ids):
        created = await api_client.post(
            "/api/v1/generations",
            headers={**headers, "Idempotency-Key": f"rl-gen-{index}"},
            json={"quote_id": quote_id, "prompt": f"hello {index}"},
        )
        assert created.status_code == 201, created.text

    quote3 = await api_client.post(
        "/api/v1/wallet/quote",
        headers=headers,
        json={"model_slug": "mock-text", "params": {}},
    )
    blocked = await api_client.post(
        "/api/v1/generations",
        headers={**headers, "Idempotency-Key": "rl-gen-block"},
        json={"quote_id": quote3.json()["quote_id"], "prompt": "blocked"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
