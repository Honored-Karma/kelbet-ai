"""Generation pipeline E2E: create → queue → runner → wallet capture/release."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.db.models.asset import GenerationAsset
from kelbet.db.models.generation import GenerationJob
from kelbet.db.models.notification import NotificationOutbox
from kelbet.db.models.wallet import Wallet
from kelbet.queue import InlineGenerationQueue
from kelbet.services.generation_runner import GenerationRunner
from kelbet.storage import MemoryObjectStorage

BOT_TOKEN = "999:TEST-TOKEN-GEN"
GOOGLE_WEBHOOK_KEY = b"g" * 32
GOOGLE_WEBHOOK_SECRET = f"whsec_{base64.b64encode(GOOGLE_WEBHOOK_KEY).decode('ascii')}"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _user_json(*, telegram_id: int, language_code: str = "ru") -> str:
    return json.dumps(
        {
            "id": telegram_id,
            "username": f"gen_{telegram_id}",
            "language_code": language_code,
            "first_name": "Gen",
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
def gen_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("QUOTE_TTL_SECONDS", "600")
    monkeypatch.setenv("WELCOME_CREDITS", "20")
    monkeypatch.setenv("WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("GOOGLE_WEBHOOK_SIGNING_SECRETS", GOOGLE_WEBHOOK_SECRET)
    monkeypatch.setenv("GENERATION_QUEUE_BACKEND", "inline")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    gen_settings: Settings,
) -> AsyncIterator[tuple[AsyncClient, object]]:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)

    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    queue = InlineGenerationQueue()
    app.state.generation_queue = queue
    storage = MemoryObjectStorage(bucket_name="kelbet-assets")
    app.state.object_storage = storage
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app


async def _login(client: AsyncClient, telegram_id: int) -> str:
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed_init_data(telegram_id=telegram_id)},
    )
    assert auth.status_code == 200, auth.text
    return auth.json()["access_token"]  # type: ignore[no-any-return]


async def _quote(client: AsyncClient, token: str, *, model_slug: str = "mock-image") -> str:
    response = await client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": model_slug, "params": {"resolution": "720p", "aspect_ratio": "1:1"}},
    )
    assert response.status_code == 200, response.text
    return response.json()["quote_id"]  # type: ignore[no-any-return]


async def _quote_params(
    client: AsyncClient,
    token: str,
    *,
    model_slug: str,
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": model_slug, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


async def _upload_ready_image(
    client: AsyncClient,
    app: object,
    token: str,
) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    presign = await client.post(
        "/api/v1/uploads/presign",
        headers=headers,
        json={
            "content_type": "image/png",
            "byte_size": len(PNG_BYTES),
            "role": "input",
        },
    )
    assert presign.status_code == 200, presign.text
    body = presign.json()
    storage: MemoryObjectStorage = app.state.object_storage  # type: ignore[attr-defined]
    storage.put_bytes(body["object_key"], PNG_BYTES, content_type="image/png")
    complete = await client.post(
        f"/api/v1/uploads/{body['asset_id']}/complete",
        headers=headers,
    )
    assert complete.status_code == 200, complete.text
    return body["asset_id"]  # type: ignore[no-any-return]


async def _drain_queue(
    app: object,
    session_factory: async_sessionmaker[AsyncSession],
) -> list[str]:
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    storage = app.state.object_storage  # type: ignore[attr-defined]
    statuses: list[str] = []
    for generation_id, _modality in queue.pop_all():
        async with session_factory() as session, session.begin():
            status = await GenerationRunner(session, storage).process(generation_id)
            statuses.append(status.value)
    return statuses


@pytest.mark.asyncio
async def test_generation_happy_path_capture(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 710001)
    quote_id = await _quote(client, token)
    correlation_id = str(uuid4())

    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-happy-1",
            "X-Correlation-ID": correlation_id,
        },
        json={"quote_id": quote_id, "prompt": "a red cube"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "queued"
    assert body["user_credit_price"] == 5
    gen_id = body["id"]

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        job = (await session.execute(select(GenerationJob))).scalar_one()
        assert wallet.balance == 20
        assert wallet.reserved == 5
        assert str(job.correlation_id) == correlation_id

    statuses = await _drain_queue(app, session_factory)
    assert statuses == ["succeeded"]

    async with session_factory() as session, session.begin():
        outbox = (await session.execute(select(NotificationOutbox))).scalar_one()
        assert str(outbox.generation_id) == gen_id
        assert outbox.status == "pending"

    got = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.status_code == 200
    detail = got.json()
    assert detail["status"] == "succeeded"
    assert len(detail["output_asset_ids"]) == 1

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 15
        assert wallet.reserved == 0

    history = await client.get(
        "/api/v1/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    history_item = history.json()["items"][0]
    assert history_item["id"] == gen_id
    assert history_item["preview_asset_id"] == detail["output_asset_ids"][0]
    assert history_item["preview_content_type"] == "image/png"

    downloads = await client.post(
        "/api/v1/assets/downloads",
        headers={"Authorization": f"Bearer {token}"},
        json={"asset_ids": [history_item["preview_asset_id"]]},
    )
    assert downloads.status_code == 200
    assert downloads.json()["items"][0]["id"] == history_item["preview_asset_id"]
    assert downloads.json()["items"][0]["download_url"].startswith("data:image/png")
    assert downloads.json()["items"][0]["width"] == 1
    assert downloads.json()["items"][0]["height"] == 1


@pytest.mark.asyncio
async def test_generation_fail_releases_hold(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 710002)
    quote_id = await _quote(client, token)

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-fail-1"},
        json={"quote_id": quote_id, "prompt": "fail"},
    )
    assert created.status_code == 201, created.text
    gen_id = created.json()["id"]

    statuses = await _drain_queue(app, session_factory)
    assert statuses == ["failed"]

    got = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "failed"
    assert got.json()["error_code"] == "mock_forced_failure"

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 20
        assert wallet.reserved == 0


@pytest.mark.asyncio
async def test_cancel_queued_releases_hold(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 710003)
    quote_id = await _quote(client, token)

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-cancel-1"},
        json={"quote_id": quote_id, "prompt": "cancel me"},
    )
    gen_id = created.json()["id"]

    cancelled = await client.post(
        f"/api/v1/generations/{gen_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 20
        assert wallet.reserved == 0

    # Queue item may still be present; runner should no-op on terminal
    statuses = await _drain_queue(app, session_factory)
    assert statuses == ["cancelled"]


@pytest.mark.asyncio
async def test_idempotent_create_returns_same_generation(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, _app = api_client
    token = await _login(client, 710004)
    quote_id = await _quote(client, token)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-same-key"}
    payload = {"quote_id": quote_id, "prompt": "same"}

    first = await client.post("/api/v1/generations", headers=headers, json=payload)
    second = await client.post("/api/v1/generations", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_generation_enforces_model_input_requirements(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, app = api_client
    token = await _login(client, 710008)
    first_asset = await _upload_ready_image(client, app, token)
    second_asset = await _upload_ready_image(client, app, token)

    text_quote = await client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": "mock-text", "params": {}},
    )
    assert text_quote.status_code == 200, text_quote.text
    forbidden = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-forbidden-input",
        },
        json={
            "quote_id": text_quote.json()["quote_id"],
            "prompt": "describe this",
            "input_asset_ids": [first_asset],
        },
    )
    assert forbidden.status_code == 422
    assert forbidden.json()["error"]["code"] == "upload_validation_error"

    image_quote = await _quote(client, token)
    too_many = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-too-many-inputs",
        },
        json={
            "quote_id": image_quote,
            "prompt": "combine these references",
            "input_asset_ids": [first_asset, second_asset],
        },
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "upload_validation_error"


@pytest.mark.asyncio
async def test_edit_accepts_ordered_references_and_upscale_requires_one(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, app = api_client
    token = await _login(client, 710012)
    references = [
        await _upload_ready_image(client, app, token),
        await _upload_ready_image(client, app, token),
        await _upload_ready_image(client, app, token),
    ]

    edit_quote = await _quote_params(
        client,
        token,
        model_slug="runway-seedream5-lite-edit",
        params={"resolution": "2k", "aspect_ratio": "1:1"},
    )
    edit = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-three-ordered-references",
        },
        json={
            "quote_id": edit_quote["quote_id"],
            "prompt": "Keep Figure 1, use Figure 2 and Figure 3 as visual references",
            "input_asset_ids": references,
            "rights_consent_confirmed": True,
            "rights_consent_version": "2026-08-01-v1",
        },
    )
    assert edit.status_code == 201, edit.text
    assert edit.json()["modality"] == "image_edit"

    upscale_quote = await _quote_params(
        client,
        token,
        model_slug="runway-magnific-image-upscale",
    )
    missing_source = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-upscale-missing-source",
        },
        json={"quote_id": upscale_quote["quote_id"], "prompt": ""},
    )
    assert missing_source.status_code == 422
    assert missing_source.json()["error"]["code"] == "upload_validation_error"

    forbidden_prompt = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-upscale-forbidden-prompt",
        },
        json={
            "quote_id": upscale_quote["quote_id"],
            "prompt": "make it larger",
            "input_asset_ids": [references[0]],
        },
    )
    assert forbidden_prompt.status_code == 422
    assert forbidden_prompt.json()["error"]["code"] == "upload_validation_error"


@pytest.mark.asyncio
async def test_generation_enforces_catalog_prompt_limit(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, _app = api_client
    token = await _login(client, 710009)
    quote_id = await _quote(client, token)
    response = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-long-prompt",
        },
        json={"quote_id": quote_id, "prompt": "x" * 2001},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "upload_validation_error"


@pytest.mark.asyncio
async def test_generation_draft_restores_owned_request_and_omits_expired_reference(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    owner = await _login(client, 710010)
    other = await _login(client, 710011)
    asset_id = await _upload_ready_image(client, app, owner)
    quote_id = await _quote(client, owner)
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {owner}",
            "Idempotency-Key": "idem-draft-source",
        },
        json={
            "quote_id": quote_id,
            "prompt": "premium ceramic product on warm stone",
            "input_asset_ids": [asset_id],
        },
    )
    assert created.status_code == 201, created.text
    generation_id = created.json()["id"]

    draft = await client.get(
        f"/api/v1/generations/{generation_id}/draft",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert draft.status_code == 200, draft.text
    assert draft.json() == {
        "source_generation_id": generation_id,
        "mode": "repeat",
        "model_slug": "mock-image",
        "modality": "image",
        "prompt": "premium ceramic product on warm stone",
        "params": {"resolution": "720p", "aspect_ratio": "1:1"},
        "input_asset_ids": [asset_id],
        "unavailable_asset_ids": [],
        "missing_input_assets": 0,
        "model_available": True,
        "replacement_slug": None,
        "template_id": None,
        "template_slug": None,
        "template_version": None,
        "template_inputs": {},
    }

    stolen = await client.get(
        f"/api/v1/generations/{generation_id}/draft",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert stolen.status_code == 404

    statuses = await _drain_queue(app, session_factory)
    assert statuses == ["succeeded"]
    completed = await client.get(
        f"/api/v1/generations/{generation_id}",
        headers={"Authorization": f"Bearer {owner}"},
    )
    output_asset_id = completed.json()["output_asset_ids"][0]

    remix_draft = await client.get(
        f"/api/v1/generations/{generation_id}/draft?mode=remix",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert remix_draft.status_code == 200, remix_draft.text
    assert remix_draft.json()["mode"] == "remix"
    assert remix_draft.json()["input_asset_ids"] == [output_asset_id]
    assert remix_draft.json()["missing_input_assets"] == 0

    upscale_draft = await client.get(
        f"/api/v1/generations/{generation_id}/draft?mode=upscale",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert upscale_draft.status_code == 200, upscale_draft.text
    assert upscale_draft.json()["mode"] == "upscale"
    assert upscale_draft.json()["input_asset_ids"] == [output_asset_id]

    remix_quote = await _quote(client, owner)
    remix = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {owner}",
            "Idempotency-Key": "idem-remix-output",
        },
        json={
            "quote_id": remix_quote,
            "prompt": "make a cooler evening variation",
            "input_asset_ids": [output_asset_id],
        },
    )
    assert remix.status_code == 201, remix.text

    other_quote = await _quote(client, other)
    stolen_output = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {other}",
            "Idempotency-Key": "idem-stolen-remix-output",
        },
        json={
            "quote_id": other_quote,
            "prompt": "steal the reference",
            "input_asset_ids": [output_asset_id],
        },
    )
    assert stolen_output.status_code == 404

    hidden_batch = await client.post(
        "/api/v1/assets/downloads",
        headers={"Authorization": f"Bearer {other}"},
        json={"asset_ids": [output_asset_id]},
    )
    assert hidden_batch.status_code == 200
    assert hidden_batch.json()["items"] == []

    async with session_factory() as session, session.begin():
        asset = await session.get(GenerationAsset, UUID(asset_id))
        assert asset is not None
        asset.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    expired = await client.get(
        f"/api/v1/generations/{generation_id}/draft",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert expired.status_code == 200
    assert expired.json()["input_asset_ids"] == []
    assert expired.json()["missing_input_assets"] == 1

    hidden_asset = await client.get(
        f"/api/v1/assets/{asset_id}",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert hidden_asset.status_code == 404


@pytest.mark.asyncio
async def test_runner_rejects_reference_that_expires_after_enqueue(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 710012)
    asset_id = await _upload_ready_image(client, app, token)
    quote_id = await _quote(client, token)
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-expire-after-queue",
        },
        json={
            "quote_id": quote_id,
            "prompt": "reference must still exist at execution time",
            "input_asset_ids": [asset_id],
        },
    )
    assert created.status_code == 201, created.text

    async with session_factory() as session, session.begin():
        asset = await session.get(GenerationAsset, UUID(asset_id))
        assert asset is not None
        asset.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    assert await _drain_queue(app, session_factory) == ["failed"]
    generation = await client.get(
        f"/api/v1/generations/{created.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generation.json()["error_code"] == "input_asset_unavailable"

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 20
        assert wallet.reserved == 0


@pytest.mark.asyncio
async def test_idor_generation_404(api_client: tuple[AsyncClient, object]) -> None:
    client, _app = api_client
    owner = await _login(client, 710005)
    other = await _login(client, 710006)
    quote_id = await _quote(client, owner)

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {owner}", "Idempotency-Key": "idem-idor"},
        json={"quote_id": quote_id, "prompt": "secret"},
    )
    gen_id = created.json()["id"]

    response = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert response.status_code == 404

    missing = await client.get(
        f"/api/v1/generations/{uuid4()}",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_webhook_duplicate_receipt(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 710007)
    quote_id = await _quote(client, token)
    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-wh-1"},
        json={"quote_id": quote_id, "prompt": "via webhook"},
    )
    gen_id = created.json()["id"]
    # Clear inline queue — webhook path drives the runner
    app.state.generation_queue.pop_all()  # type: ignore[attr-defined]

    payload = {"generation_id": gen_id, "type": "completed", "event_id": "evt-1"}
    headers = {
        "X-Kelbet-Webhook-Secret": "test-webhook-secret",
        "X-Event-Id": "evt-1",
    }
    first = await client.post("/api/v1/webhooks/mock", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json() == {"ok": True, "duplicate": False}

    second = await client.post("/api/v1/webhooks/mock", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    queued = app.state.generation_queue.pop_all()  # type: ignore[attr-defined]
    assert queued == [(UUID(gen_id), "image")]
    async with session_factory() as session, session.begin():
        await GenerationRunner(
            session,
            app.state.object_storage,  # type: ignore[attr-defined]
        ).process(UUID(gen_id))

    got = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "succeeded"

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 15
        assert wallet.reserved == 0


@pytest.mark.asyncio
async def test_google_video_webhook_signature_wakes_worker_once(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 710008)
    quote_id = await _quote(client, token)
    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-google-wh"},
        json={"quote_id": quote_id, "prompt": "google webhook"},
    )
    generation_id = UUID(created.json()["id"])
    app.state.generation_queue.pop_all()  # type: ignore[attr-defined]

    operation_id = "models/veo-3.1-lite-generate-preview/operations/op-webhook-1"
    future_poll = datetime.now(UTC) + timedelta(minutes=5)
    async with session_factory() as session, session.begin():
        job = (
            await session.execute(select(GenerationJob).where(GenerationJob.id == generation_id))
        ).scalar_one()
        job.provider = "google"
        job.provider_model_id = "veo-3.1-lite-generate-preview"
        job.provider_job_id = operation_id
        job.modality = "video"
        job.status = "running"
        job.next_poll_at = future_poll

    raw = json.dumps(
        {
            "type": "video.generated",
            "version": "v1",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "id": operation_id,
                "output_file_uri": "https://google.test/files/video.mp4",
            },
        },
        separators=(",", ":"),
    ).encode()
    webhook_id = "msg_google_video_1"
    timestamp = str(int(datetime.now(UTC).timestamp()))
    signed = f"{webhook_id}.{timestamp}.".encode() + raw
    signature = base64.b64encode(
        hmac.new(GOOGLE_WEBHOOK_KEY, signed, hashlib.sha256).digest()
    ).decode()
    headers = {
        "content-type": "application/json",
        "webhook-id": webhook_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": f"v1,{signature}",
    }

    first = await client.post("/api/v1/webhooks/google", content=raw, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json() == {"ok": True, "duplicate": False}
    assert app.state.generation_queue.pop_all() == [  # type: ignore[attr-defined]
        (generation_id, "video")
    ]

    second = await client.post("/api/v1/webhooks/google", content=raw, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert app.state.generation_queue.pop_all() == []  # type: ignore[attr-defined]

    async with session_factory() as session:
        job = (
            await session.execute(select(GenerationJob).where(GenerationJob.id == generation_id))
        ).scalar_one()
        assert job.webhook_last_event_id == webhook_id
        assert job.next_poll_at is not None
        assert job.next_poll_at < future_poll


@pytest.mark.asyncio
async def test_google_video_webhook_rejects_unsigned_request(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, _ = api_client
    response = await client.post(
        "/api/v1/webhooks/google",
        json={"type": "video.generated", "data": {"id": "operations/forged"}},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "webhook_verification_failed"


@pytest.mark.asyncio
async def test_generic_webhook_requires_secret_and_handles_unknown_generation(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, app = api_client
    forged = await client.post(
        "/api/v1/webhooks/mock",
        json={"event_id": "evt-forged", "generation_id": "not-a-uuid"},
    )
    assert forged.status_code == 401
    assert forged.json()["error"]["code"] == "webhook_verification_failed"

    accepted = await client.post(
        "/api/v1/webhooks/mock",
        headers={
            "X-Kelbet-Webhook-Secret": "test-webhook-secret",
            "X-Event-Id": "evt-unknown-generation",
        },
        json={"generation_id": "not-a-uuid", "type": "completed"},
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"ok": True, "duplicate": False}
    assert app.state.generation_queue.pop_all() == []  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_passport_reports_the_run_that_actually_happened(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The passport is the receipt: which model served the request, at what size, for what."""

    client, app = api_client
    token = await _login(client, 715001)
    quote_id = await _quote(client, token)

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-passport-1"},
        json={"quote_id": quote_id, "prompt": "a blue cube"},
    )
    assert created.status_code == 201, created.text
    gen_id = created.json()["id"]

    # Present before the work starts: the quoted route is already a commitment.
    queued_passport = created.json()["passport"]
    assert queued_passport["provider"] == "mock"
    assert queued_passport["substituted"] is False
    assert queued_passport["credits_charged"] == 5
    assert queued_passport["resolution"] == "720p"
    assert queued_passport["aspect_ratio"] == "1:1"
    assert queued_passport["width"] is None  # nothing delivered yet

    assert await _drain_queue(app, session_factory) == ["succeeded"]

    detail = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    passport = detail.json()["passport"]
    assert passport["provider"] == "mock"
    assert passport["provider_model_id"] == "mock-image-v1"
    assert passport["requested_provider"] == "mock"
    assert passport["requested_provider_model_id"] == "mock-image-v1"
    assert passport["substituted"] is False
    assert passport["credits_charged"] == 5
    assert passport["attempts"] == 1
    # Measured from the delivered file, which is the one claim a provider cannot inflate.
    assert passport["width"] == 1
    assert passport["height"] == 1


@pytest.mark.asyncio
async def test_passport_declares_a_substituted_model(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A fallback must be disclosed, not absorbed into the model_slug the user picked.

    `model_slug` stays the SKU that was bought, so without this field a route that
    quietly served a different model would be indistinguishable from one that did not.
    """

    client, _app = api_client
    token = await _login(client, 715002)
    quote_id = await _quote(client, token)

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-passport-2"},
        json={"quote_id": quote_id, "prompt": "a green cube"},
    )
    assert created.status_code == 201
    gen_id = created.json()["id"]

    # Stand in for a mid-flight fallback: the served route no longer matches the quote.
    async with session_factory() as session, session.begin():
        job = (
            await session.execute(select(GenerationJob).where(GenerationJob.id == UUID(gen_id)))
        ).scalar_one()
        job.provider = "google"
        job.provider_model_id = "veo-3.1-lite-generate-preview"

    detail = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    passport = detail.json()["passport"]
    assert passport["substituted"] is True
    assert passport["provider"] == "google"
    assert passport["provider_model_id"] == "veo-3.1-lite-generate-preview"
    # And it still says what was promised, so the two can be compared.
    assert passport["requested_provider"] == "mock"
    assert passport["requested_provider_model_id"] == "mock-image-v1"
    assert detail.json()["model_slug"] == "mock-image"


@pytest.mark.asyncio
async def test_ledger_shows_every_movement_and_links_the_charge_to_its_generation(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 715003)
    quote_id = await _quote(client, token)

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-ledger-1"},
        json={"quote_id": quote_id, "prompt": "a yellow cube"},
    )
    assert created.status_code == 201
    gen_id = created.json()["id"]
    assert await _drain_queue(app, session_factory) == ["succeeded"]

    ledger = await client.get(
        "/api/v1/wallet/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ledger.status_code == 200
    items = ledger.json()["items"]
    assert len(items) == 2

    # Newest first: the charge for the generation, then the welcome bonus.
    charge, welcome = items
    assert charge["type"] == "debit"
    assert charge["reason"] == "generation_capture"
    assert charge["amount"] == -5
    assert charge["generation_id"] == gen_id
    assert welcome["type"] == "credit"
    assert welcome["reason"] == "welcome_bonus"
    assert welcome["generation_id"] is None
    # Running balance is carried on every line, so a user can audit the arithmetic.
    assert welcome["balance_after"] - 5 == charge["balance_after"]


@pytest.mark.asyncio
async def test_ledger_never_shows_another_wallet(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, _app = api_client
    mine = await _login(client, 715004)
    theirs = await _login(client, 715005)

    quote_id = await _quote(client, mine)
    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {mine}", "Idempotency-Key": "idem-ledger-2"},
        json={"quote_id": quote_id, "prompt": "a private cube"},
    )
    assert created.status_code == 201

    other = await client.get(
        "/api/v1/wallet/transactions",
        headers={"Authorization": f"Bearer {theirs}"},
    )
    assert other.status_code == 200
    reasons = [item["reason"] for item in other.json()["items"]]
    # A hold is not a movement, so the other wallet holds only its own welcome bonus.
    assert reasons == ["welcome_bonus"]


@pytest.mark.asyncio
async def test_ledger_requires_a_session(api_client: tuple[AsyncClient, object]) -> None:
    client, _app = api_client
    response = await client.get("/api/v1/wallet/transactions")
    assert response.status_code == 401
