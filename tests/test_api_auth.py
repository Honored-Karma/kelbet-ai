"""API auth + /me integration tests."""

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

BOT_TOKEN = "999:TEST-TOKEN-KELBET"


def _user_json(*, telegram_id: int = 777001, language_code: str = "kk") -> str:
    return json.dumps(
        {
            "id": telegram_id,
            "username": "mini_user",
            "language_code": language_code,
            "first_name": "Mini",
        },
        separators=(",", ":"),
    )


def _signed_init_data(
    *,
    telegram_id: int = 777001,
    auth_dt: datetime | None = None,
    language_code: str = "kk",
) -> str:
    when = auth_dt or datetime.now(UTC)
    return sign_init_data(
        {
            "auth_date": str(int(when.timestamp())),
            "user": _user_json(telegram_id=telegram_id, language_code=language_code),
            "query_id": f"q-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("CORS_ORIGINS", "https://web.telegram.org")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_me_requires_auth(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "invalid_session"


@pytest.mark.asyncio
async def test_auth_telegram_and_me(api_client: AsyncClient, auth_settings: Settings) -> None:
    init_data = _signed_init_data()
    auth = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert auth.status_code == 200, auth.text
    payload = auth.json()
    assert payload["token_type"] == "bearer"
    assert payload["welcome_applied"] is True
    assert payload["user"]["telegram_id"] == 777001
    assert payload["user"]["language"] == "kk"
    token = payload["access_token"]

    me = await api_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["telegram_id"] == 777001
    # Derived from the configured bonus, not a copy of it: the welcome amount is
    # a product decision that moves, and a hardcoded number here just fails
    # later without saying anything about the endpoint under test.
    assert me_body["balance"] == auth_settings.welcome_credits
    assert me_body["reserved"] == 0
    assert me_body["available"] == auth_settings.welcome_credits


@pytest.mark.asyncio
async def test_forged_init_data_rejected(api_client: AsyncClient) -> None:
    init_data = _signed_init_data()
    forged = init_data.replace("mini_user", "hacker")
    response = await api_client.post("/api/v1/auth/telegram", json={"init_data": forged})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_init_data"


@pytest.mark.asyncio
async def test_expired_init_data_rejected(api_client: AsyncClient) -> None:
    init_data = _signed_init_data(auth_dt=datetime(2020, 1, 1, tzinfo=UTC))
    response = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "expired_init_data"


@pytest.mark.asyncio
async def test_replay_init_data_rejected(api_client: AsyncClient) -> None:
    init_data = _signed_init_data(telegram_id=777002)
    first = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert first.status_code == 200
    second = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "replay_init_data"


@pytest.mark.asyncio
async def test_logout_revokes_session(api_client: AsyncClient) -> None:
    init_data = _signed_init_data(telegram_id=777003)
    auth = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    token = auth.json()["access_token"]

    logout = await api_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout.status_code == 200
    assert logout.json()["revoked"] is True

    me = await api_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_patch_me_language(api_client: AsyncClient) -> None:
    init_data = _signed_init_data(telegram_id=777004, language_code="kk")
    auth = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    token = auth.json()["access_token"]

    patched = await api_client.patch(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"language": "ru"},
    )
    assert patched.status_code == 200
    assert patched.json()["language"] == "ru"
    assert patched.json()["notify_generation_ready"] is True

    notification_patched = await api_client.patch(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"notify_generation_ready": False},
    )
    assert notification_patched.status_code == 200
    assert notification_patched.json()["notify_generation_ready"] is False


@pytest.mark.asyncio
async def test_ready_endpoint(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
