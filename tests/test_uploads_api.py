"""Upload API integration tests (memory storage, no remote URL fetch)."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.config import Settings, get_settings
from kelbet.storage.memory import MemoryObjectStorage

BOT_TOKEN = "999:TEST-TOKEN-UPLOADS"

# Minimal valid-looking headers
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
FAKE_TEXT = b"not-an-image-file-content!!!!!!"


def _user_json(*, telegram_id: int) -> str:
    return json.dumps(
        {
            "id": telegram_id,
            "username": "uploader",
            "language_code": "ru",
            "first_name": "Up",
        },
        separators=(",", ":"),
    )


def _signed_init_data(*, telegram_id: int) -> str:
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": _user_json(telegram_id=telegram_id),
            "query_id": f"q-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def upload_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "1048576")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    upload_settings: Settings,
) -> AsyncIterator[tuple[AsyncClient, MemoryObjectStorage]]:
    storage = MemoryObjectStorage(bucket_name="kelbet-assets")
    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    app.state.object_storage = storage
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, storage


async def _login(client: AsyncClient, telegram_id: int) -> str:
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed_init_data(telegram_id=telegram_id)},
    )
    assert auth.status_code == 200, auth.text
    return auth.json()["access_token"]  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_presign_and_complete_happy_path(
    api_client: tuple[AsyncClient, MemoryObjectStorage],
) -> None:
    client, storage = api_client
    token = await _login(client, 900001)
    presign = await client.post(
        "/api/v1/uploads/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/jpeg", "byte_size": len(JPEG_BYTES), "role": "input"},
    )
    assert presign.status_code == 200, presign.text
    body = presign.json()
    assert body["upload_url"].startswith("memory://")
    assert ".." not in body["object_key"]
    assert body["object_key"].startswith("inputs/")

    storage.put_bytes(body["object_key"], JPEG_BYTES, content_type="image/jpeg")
    complete = await client.post(
        f"/api/v1/uploads/{body['asset_id']}/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert complete.status_code == 200, complete.text
    done = complete.json()
    assert done["status"] == "ready"
    assert done["magic_ok"] is True
    assert done["byte_size"] == len(JPEG_BYTES)
    assert done["width"] is None
    assert done["height"] is None

    download = await client.get(
        f"/api/v1/assets/{body['asset_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download.status_code == 200, download.text
    asset = download.json()
    assert asset["id"] == body["asset_id"]
    assert asset["role"] == "input"
    assert asset["content_type"] == "image/jpeg"
    assert asset["byte_size"] == len(JPEG_BYTES)
    assert asset["download_url"] == (
        "data:image/jpeg;base64," + base64.b64encode(JPEG_BYTES).decode("ascii")
    )
    assert asset["expires_in"] > 0


@pytest.mark.asyncio
async def test_reject_bad_mime_and_magic(
    api_client: tuple[AsyncClient, MemoryObjectStorage],
) -> None:
    client, storage = api_client
    token = await _login(client, 900002)

    bad_mime = await client.post(
        "/api/v1/uploads/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "application/pdf", "byte_size": 100},
    )
    assert bad_mime.status_code == 422

    too_big = await client.post(
        "/api/v1/uploads/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/png", "byte_size": 10_000_000},
    )
    assert too_big.status_code == 422

    presign = await client.post(
        "/api/v1/uploads/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/png", "byte_size": len(FAKE_TEXT)},
    )
    assert presign.status_code == 200
    key = presign.json()["object_key"]
    asset_id = presign.json()["asset_id"]
    storage.put_bytes(key, FAKE_TEXT, content_type="image/png")
    complete = await client.post(
        f"/api/v1/uploads/{asset_id}/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert complete.status_code == 422
    assert complete.json()["error"]["code"] == "upload_validation_error"


@pytest.mark.asyncio
async def test_idor_other_users_asset(
    api_client: tuple[AsyncClient, MemoryObjectStorage],
) -> None:
    client, storage = api_client
    owner = await _login(client, 900003)
    other = await _login(client, 900004)
    presign = await client.post(
        "/api/v1/uploads/presign",
        headers={"Authorization": f"Bearer {owner}"},
        json={"content_type": "image/jpeg", "byte_size": len(JPEG_BYTES)},
    )
    asset_id = presign.json()["asset_id"]
    storage.put_bytes(presign.json()["object_key"], JPEG_BYTES, content_type="image/jpeg")

    stolen = await client.post(
        f"/api/v1/uploads/{asset_id}/complete",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert stolen.status_code == 404

    storage.put_bytes(presign.json()["object_key"], JPEG_BYTES, content_type="image/jpeg")
    complete = await client.post(
        f"/api/v1/uploads/{asset_id}/complete",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert complete.status_code == 200

    stolen_download = await client.get(
        f"/api/v1/assets/{asset_id}",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert stolen_download.status_code == 404


@pytest.mark.asyncio
async def test_pending_asset_cannot_be_downloaded(
    api_client: tuple[AsyncClient, MemoryObjectStorage],
) -> None:
    client, _storage = api_client
    token = await _login(client, 900007)
    presign = await client.post(
        "/api/v1/uploads/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/png", "byte_size": len(PNG_BYTES)},
    )
    assert presign.status_code == 200

    pending = await client.get(
        f"/api/v1/assets/{presign.json()['asset_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pending.status_code == 404


@pytest.mark.asyncio
async def test_api_has_no_remote_url_fetch_endpoint(
    api_client: tuple[AsyncClient, MemoryObjectStorage],
) -> None:
    """SSRF guard: uploads accept only asset_id after presign, never arbitrary URLs."""
    client, _storage = api_client
    token = await _login(client, 900005)
    # No fetch-by-url route should exist
    for path in (
        "/api/v1/uploads/fetch",
        "/api/v1/uploads/from-url",
        "/api/v1/assets/fetch",
    ):
        response = await client.post(
            path,
            headers={"Authorization": f"Bearer {token}"},
            json={"url": "http://169.254.169.254/latest/meta-data/"},
        )
        assert response.status_code in {404, 405, 422}


@pytest.mark.asyncio
async def test_object_key_is_uuid_safe(
    api_client: tuple[AsyncClient, MemoryObjectStorage],
) -> None:
    client, _storage = api_client
    token = await _login(client, 900006)
    presign = await client.post(
        "/api/v1/uploads/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/webp", "byte_size": 128},
    )
    key = presign.json()["object_key"]
    parts = key.split("/")
    assert parts[0] == "inputs"
    UUID(parts[1])  # user_id
    UUID(parts[2])  # asset_id
    assert parts[3].endswith(".webp")
