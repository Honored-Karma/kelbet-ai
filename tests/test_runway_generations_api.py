"""Stage H: Runway image/video async path — poll, timeout, video concurrency."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from apps.api.main import create_app
from apps.worker.main import (
    ImageWorkerSettings,
    MaintainWorkerSettings,
    TextWorkerSettings,
    VideoWorkerSettings,
)
from arq.connections import RedisSettings
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.db.models.catalog import FeatureFlag
from kelbet.db.models.generation import GenerationAttempt, GenerationJob, ProviderUsage
from kelbet.db.models.wallet import Wallet
from kelbet.providers.base import GenerationOutput, GenerationProviderResult, GenerationRequest
from kelbet.providers.runway import RunwayProvider
from kelbet.queue import InlineGenerationQueue
from kelbet.services.generation_runner import GenerationRunner
from kelbet.storage import MemoryObjectStorage

BOT_TOKEN = "999:TEST-TOKEN-RUNWAY"
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class StickyAsyncProvider:
    """Returns accepted on generate; scripted get_status results."""

    def __init__(self, polls: list[GenerationProviderResult]) -> None:
        self._polls = list(polls)
        self.cancel_calls = 0
        self.requests: list[GenerationRequest] = []

    @property
    def name(self) -> str:
        return "runway"

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        self.requests.append(request)
        return GenerationProviderResult(
            status="accepted",
            provider_job_id=f"task-{request.generation_id.hex[:8]}",
        )

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        if not self._polls:
            return GenerationProviderResult(status="accepted", provider_job_id=provider_job_id)
        return self._polls.pop(0)

    async def cancel(self, provider_job_id: str) -> None:
        self.cancel_calls += 1


class ImmediateProvider:
    def __init__(self, result: GenerationProviderResult, *, name: str) -> None:
        self.result = result
        self.provider_name = name
        self.requests: list[GenerationRequest] = []

    @property
    def name(self) -> str:
        return self.provider_name

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        self.requests.append(request)
        return self.result

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        del provider_job_id
        return self.result

    async def cancel(self, provider_job_id: str) -> None:
        del provider_job_id


def _signed_init_data(*, telegram_id: int) -> str:
    user = json.dumps(
        {
            "id": telegram_id,
            "username": f"rw_{telegram_id}",
            "language_code": "ru",
            "first_name": "Rw",
        },
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
def runway_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("QUOTE_TTL_SECONDS", "600")
    monkeypatch.setenv("WELCOME_CREDITS", "500")
    monkeypatch.setenv("RUNWAY_API_KEY", "test-runway")
    monkeypatch.setenv("RUNWAY_POLL_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("RUNWAY_IMAGE_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("GENERATION_QUEUE_BACKEND", "inline")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    runway_settings: Settings,
) -> AsyncIterator[tuple[AsyncClient, object]]:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)

    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    app.state.generation_queue = InlineGenerationQueue()
    app.state.object_storage = MemoryObjectStorage(bucket_name="kelbet-assets")
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


async def _quote(client: AsyncClient, token: str, *, model_slug: str) -> str:
    params: dict[str, object] = {}
    if "image" in model_slug:
        params = {"resolution": "720p", "aspect_ratio": "1:1"}
    elif "video" in model_slug:
        params = {
            "duration_sec": 4,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        }
    response = await client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": model_slug, "params": params},
    )
    assert response.status_code == 200, response.text
    return response.json()["quote_id"]  # type: ignore[no-any-return]


def test_video_worker_concurrency_limit() -> None:
    assert VideoWorkerSettings.queue_name == "kelbet:video"
    assert VideoWorkerSettings.max_jobs == 2


def test_arq_worker_settings_use_resolved_values() -> None:
    worker_settings = (
        ImageWorkerSettings,
        TextWorkerSettings,
        VideoWorkerSettings,
        MaintainWorkerSettings,
    )

    for settings in worker_settings:
        assert isinstance(settings.job_timeout, int)
        assert settings.job_timeout > 0
        assert isinstance(settings.redis_settings, RedisSettings)


@pytest.mark.asyncio
async def test_runway_image_poll_without_webhook_captures(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 910001)
    quote_id = await _quote(client, token, model_slug="runway-gen4-image")

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "rw-img-1"},
        json={"quote_id": quote_id, "prompt": "mountains"},
    )
    assert created.status_code == 201, created.text
    gen_id = created.json()["id"]
    price = created.json()["user_credit_price"]

    provider = StickyAsyncProvider(
        [
            GenerationProviderResult(status="accepted", provider_job_id="task-sticky"),
            GenerationProviderResult(
                status="succeeded",
                provider_job_id="task-sticky",
                outputs=[GenerationOutput(content_type="image/png", data=_PNG_1X1)],
            ),
        ]
    )
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    storage = app.state.object_storage  # type: ignore[attr-defined]
    items = queue.pop_all()
    assert items

    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, provider=provider).process(items[0][0])
        assert status.value == "running"

    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, provider=provider).poll(items[0][0])
        assert status.value == "running"

    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, provider=provider).poll(items[0][0])
        assert status.value == "succeeded"

    got = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "succeeded"
    assert len(got.json()["output_asset_ids"]) == 1

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.reserved == 0
        assert wallet.balance == 500 - price


@pytest.mark.asyncio
async def test_runway_image_receives_completed_reference(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 910004)
    auth_headers = {"Authorization": f"Bearer {token}"}

    presign = await client.post(
        "/api/v1/uploads/presign",
        headers=auth_headers,
        json={
            "content_type": "image/png",
            "byte_size": len(_PNG_1X1),
            "role": "input",
        },
    )
    assert presign.status_code == 200, presign.text
    upload = presign.json()
    storage: MemoryObjectStorage = app.state.object_storage  # type: ignore[attr-defined]
    storage.put_bytes(upload["object_key"], _PNG_1X1, content_type="image/png")
    complete = await client.post(
        f"/api/v1/uploads/{upload['asset_id']}/complete",
        headers=auth_headers,
    )
    assert complete.status_code == 200, complete.text

    quote_id = await _quote(client, token, model_slug="runway-gen4-image")
    created = await client.post(
        "/api/v1/generations",
        headers={**auth_headers, "Idempotency-Key": "rw-img-reference-1"},
        json={
            "quote_id": quote_id,
            "prompt": "premium product photo",
            "input_asset_ids": [upload["asset_id"]],
        },
    )
    assert created.status_code == 201, created.text

    provider = StickyAsyncProvider([])
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]
    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, provider=provider).process(job_id)

    assert status.value == "running"
    assert len(provider.requests) == 1
    assert provider.requests[0].input_object_keys == [upload["object_key"]]
    assert provider.requests[0].input_urls[0].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_runway_timeout_releases_hold(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNWAY_IMAGE_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    settings = get_settings()

    client, app = api_client
    token = await _login(client, 910002)
    quote_id = await _quote(client, token, model_slug="runway-gen4-image")
    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "rw-to-1"},
        json={"quote_id": quote_id, "prompt": "slow"},
    )
    gen_id = created.json()["id"]

    provider = StickyAsyncProvider([])
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    storage = app.state.object_storage  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]

    async with session_factory() as session, session.begin():
        status = await GenerationRunner(
            session, storage, provider=provider, settings=settings
        ).process(job_id)
        assert status.value == "running"

    later = datetime.now(UTC) + timedelta(seconds=5)
    async with session_factory() as session, session.begin():
        status = await GenerationRunner(
            session, storage, provider=provider, settings=settings
        ).poll(job_id, now=later)
        assert status.value == "timed_out"

    assert provider.cancel_calls == 1
    got = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "timed_out"

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 500
        assert wallet.reserved == 0


@pytest.mark.asyncio
async def test_runway_video_path_via_http_fixtures(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 910003)
    quote_id = await _quote(
        client,
        token,
        model_slug="runway-gemini-omni-video-fast",
    )
    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "rw-vid-1"},
        json={"quote_id": quote_id, "prompt": "ocean"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["modality"] == "video"

    task_state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/text_to_video":
            return httpx.Response(200, json={"id": "task_video_live"})
        if request.method == "GET" and path == "/v1/tasks/task_video_live":
            task_state["n"] += 1
            if task_state["n"] == 1:
                return httpx.Response(200, json={"id": "task_video_live", "status": "RUNNING"})
            return httpx.Response(
                200,
                json={
                    "id": "task_video_live",
                    "status": "SUCCEEDED",
                    "output": ["https://cdn.runway.test/out.mp4"],
                },
            )
        if request.method == "GET" and path.endswith("/out.mp4"):
            return httpx.Response(
                200,
                content=b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
                headers={"content-type": "video/mp4"},
            )
        return httpx.Response(404, json={"path": path})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        provider = RunwayProvider(
            api_key="test-runway",
            base_url="https://api.dev.runwayml.com",
            api_version="2024-11-06",
            client=http_client,
            download_client=http_client,
            output_host_allowlist=["cdn.runway.test"],
        )
        queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
        storage = app.state.object_storage  # type: ignore[attr-defined]
        job_id = queue.pop_all()[0][0]

        async with session_factory() as session, session.begin():
            status = await GenerationRunner(session, storage, provider=provider).process(job_id)
            assert status.value == "running"

        async with session_factory() as session, session.begin():
            status = await GenerationRunner(session, storage, provider=provider).poll(job_id)
            assert status.value == "running"

        async with session_factory() as session, session.begin():
            status = await GenerationRunner(session, storage, provider=provider).poll(job_id)
            assert status.value == "succeeded"

    got = await client.get(
        f"/api/v1/generations/{created.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "succeeded"
    assert len(got.json()["output_asset_ids"]) == 1


@pytest.mark.asyncio
async def test_video_transient_failure_falls_back_without_price_change(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = api_client
    token = await _login(client, 910005)
    quote_id = await _quote(
        client,
        token,
        model_slug="runway-gemini-omni-video-fast",
    )
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "video-fallback-1",
        },
        json={"quote_id": quote_id, "prompt": "A product rotates in warm studio light"},
    )
    assert created.status_code == 201, created.text
    quoted_price = created.json()["user_credit_price"]

    primary = StickyAsyncProvider(
        [
            GenerationProviderResult(
                status="failed",
                provider_job_id="runway-primary",
                error_code="provider_unavailable",
                error_message_safe="Runway temporarily unavailable",
                meta={"http_status": 503},
            )
        ]
    )
    fallback = StickyAsyncProvider(
        [
            GenerationProviderResult(
                status="succeeded",
                provider_job_id="google-fallback",
                outputs=[
                    GenerationOutput(
                        content_type="video/mp4",
                        data=b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
                    )
                ],
            )
        ]
    )

    def route_provider(provider_name: str, **_: object) -> StickyAsyncProvider:
        return fallback if provider_name == "google" else primary

    monkeypatch.setattr(
        "kelbet.services.generation_runner.resolve_provider",
        route_provider,
    )
    settings = Settings(
        runway_api_key="test-runway",
        google_api_key="test-google",
        runway_poll_interval_seconds=1,
    )
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    storage = app.state.object_storage  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]

    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, settings=settings).process(job_id)
        assert status.value == "running"

    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, settings=settings).poll(job_id)
        assert status.value == "running"
        job = (
            await session.execute(select(GenerationJob).where(GenerationJob.id == job_id))
        ).scalar_one()
        assert job.provider == "google"
        assert job.progress_stage == "fallback_running"

    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, settings=settings).poll(job_id)
        assert status.value == "succeeded"
        usages = list(
            (
                await session.execute(
                    select(ProviderUsage)
                    .where(ProviderUsage.generation_id == job_id)
                    .order_by(ProviderUsage.created_at)
                )
            )
            .scalars()
            .all()
        )
        assert [usage.provider for usage in usages] == ["runway", "google"]
        assert usages[-1].provider_cost_units == 2000

    got = await client.get(
        f"/api/v1/generations/{created.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "succeeded"
    assert got.json()["user_credit_price"] == quoted_price


@pytest.mark.asyncio
async def test_image_transient_failure_uses_canary_fallback_and_captures_once(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = api_client
    telegram_id = 910_006
    token = await _login(client, telegram_id)
    quote_id = await _quote(client, token, model_slug="runway-gen4-image")
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "image-fallback-canary-1",
        },
        json={"quote_id": quote_id, "prompt": "A clean product photograph"},
    )
    assert created.status_code == 201, created.text
    quoted_price = created.json()["user_credit_price"]

    primary = ImmediateProvider(
        GenerationProviderResult(
            status="failed",
            error_code="provider_unavailable",
            error_message_safe="Primary temporarily unavailable",
            meta={"http_status": 503},
        ),
        name="runway",
    )
    fallback = ImmediateProvider(
        GenerationProviderResult(
            status="succeeded",
            outputs=[GenerationOutput(content_type="image/png", data=_PNG_1X1)],
            provider_cost_units=670,
        ),
        name="google",
    )

    def route_provider(provider_name: str, **_: object) -> ImmediateProvider:
        return fallback if provider_name == "google" else primary

    monkeypatch.setattr("kelbet.services.generation_runner.resolve_provider", route_provider)
    async with session_factory() as session, session.begin():
        for key in ("google_image", "image_fallback"):
            flag = await session.get(FeatureFlag, key)
            assert flag is not None
            flag.enabled = True
            flag.payload = {"telegram_ids": [telegram_id]}

    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    storage = app.state.object_storage  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]
    settings = Settings(runway_api_key="test-runway", google_api_key="test-google")
    async with session_factory() as session, session.begin():
        first = await GenerationRunner(session, storage, settings=settings).process(job_id)
        assert first.value == "succeeded"
    async with session_factory() as session, session.begin():
        replay = await GenerationRunner(session, storage, settings=settings).process(job_id)
        assert replay.value == "succeeded"
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        attempts = list(
            (
                await session.execute(
                    select(GenerationAttempt)
                    .where(GenerationAttempt.generation_id == job_id)
                    .order_by(GenerationAttempt.attempt_no)
                )
            )
            .scalars()
            .all()
        )
        usages = list(
            (
                await session.execute(
                    select(ProviderUsage)
                    .where(ProviderUsage.generation_id == job_id)
                    .order_by(ProviderUsage.created_at)
                )
            )
            .scalars()
            .all()
        )
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert job.provider == "google"
        assert job.user_credit_price == quoted_price
        assert len(attempts) == 2
        assert [row.provider for row in usages] == ["runway", "google"]
        assert wallet.reserved == 0
        assert wallet.balance == 500 - quoted_price
    assert len(primary.requests) == len(fallback.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "http_status"),
    [
        ("invalid_input", 400),
        ("moderation_rejected", 400),
        ("unsupported_capability", 404),
        ("provider_account_error", 403),
    ],
)
async def test_image_permanent_failures_never_fallback(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    http_status: int,
) -> None:
    client, app = api_client
    telegram_id = 910_100 + http_status + len(error_code)
    token = await _login(client, telegram_id)
    quote_id = await _quote(client, token, model_slug="runway-gen4-image")
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"image-permanent-{error_code}",
        },
        json={"quote_id": quote_id, "prompt": "A safe studio scene"},
    )
    assert created.status_code == 201, created.text
    primary = ImmediateProvider(
        GenerationProviderResult(
            status="failed",
            error_code=error_code,
            error_message_safe="Permanent provider rejection",
            meta={"http_status": http_status},
        ),
        name="runway",
    )
    fallback = ImmediateProvider(
        GenerationProviderResult(
            status="succeeded",
            outputs=[GenerationOutput(content_type="image/png", data=_PNG_1X1)],
        ),
        name="google",
    )

    def route_provider(provider_name: str, **_: object) -> ImmediateProvider:
        return fallback if provider_name == "google" else primary

    monkeypatch.setattr("kelbet.services.generation_runner.resolve_provider", route_provider)
    async with session_factory() as session, session.begin():
        for key in ("google_image", "image_fallback"):
            flag = await session.get(FeatureFlag, key)
            assert flag is not None
            flag.enabled = True
            flag.payload = {"telegram_ids": [telegram_id]}
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]
    async with session_factory() as session, session.begin():
        status = await GenerationRunner(
            session,
            app.state.object_storage,  # type: ignore[attr-defined]
            settings=Settings(runway_api_key="test", google_api_key="test"),
        ).process(job_id)
        assert status.value == "failed"
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 500 and wallet.reserved == 0
    assert not fallback.requests


@pytest.mark.asyncio
async def test_image_fallback_cost_ceiling_blocks_route(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = api_client
    telegram_id = 910_007
    token = await _login(client, telegram_id)
    quote_id = await _quote(client, token, model_slug="runway-gen4-image")
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "image-fallback-cost-ceiling",
        },
        json={"quote_id": quote_id, "prompt": "A neutral product scene"},
    )
    assert created.status_code == 201
    primary = ImmediateProvider(
        GenerationProviderResult(status="failed", error_code="provider_unavailable"),
        name="runway",
    )
    fallback = ImmediateProvider(
        GenerationProviderResult(
            status="succeeded",
            outputs=[GenerationOutput(content_type="image/png", data=_PNG_1X1)],
        ),
        name="google",
    )

    def route_provider(provider_name: str, **_: object) -> ImmediateProvider:
        return fallback if provider_name == "google" else primary

    monkeypatch.setattr("kelbet.services.generation_runner.resolve_provider", route_provider)
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]
    async with session_factory() as session, session.begin():
        for key in ("google_image", "image_fallback"):
            flag = await session.get(FeatureFlag, key)
            assert flag is not None
            flag.enabled = True
            flag.payload = {"telegram_ids": [telegram_id]}
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        routing = dict(job.routing_snapshot)
        fallback_route = dict(routing["fallback"])
        fallback_route["provider_cost_ceiling_units"] = 100
        routing["fallback"] = fallback_route
        job.routing_snapshot = routing
    async with session_factory() as session, session.begin():
        status = await GenerationRunner(
            session,
            app.state.object_storage,  # type: ignore[attr-defined]
            settings=Settings(runway_api_key="test", google_api_key="test"),
        ).process(job_id)
        assert status.value == "failed"
    assert not fallback.requests


@pytest.mark.asyncio
async def test_image_fallback_kill_switch_blocks_route(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = api_client
    telegram_id = 910_008
    token = await _login(client, telegram_id)
    quote_id = await _quote(client, token, model_slug="runway-gen4-image")
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "image-fallback-kill-switch",
        },
        json={"quote_id": quote_id, "prompt": "A neutral product scene"},
    )
    assert created.status_code == 201
    primary = ImmediateProvider(
        GenerationProviderResult(status="failed", error_code="provider_unavailable"),
        name="runway",
    )
    fallback = ImmediateProvider(
        GenerationProviderResult(
            status="succeeded",
            outputs=[GenerationOutput(content_type="image/png", data=_PNG_1X1)],
        ),
        name="google",
    )

    def route_provider(provider_name: str, **_: object) -> ImmediateProvider:
        return fallback if provider_name == "google" else primary

    monkeypatch.setattr("kelbet.services.generation_runner.resolve_provider", route_provider)
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]
    async with session_factory() as session, session.begin():
        provider_flag = await session.get(FeatureFlag, "google_image")
        kill_switch = await session.get(FeatureFlag, "image_fallback")
        assert provider_flag is not None and kill_switch is not None
        provider_flag.enabled = True
        provider_flag.payload = {"telegram_ids": [telegram_id]}
        kill_switch.enabled = False
    async with session_factory() as session, session.begin():
        status = await GenerationRunner(
            session,
            app.state.object_storage,  # type: ignore[attr-defined]
            settings=Settings(runway_api_key="test", google_api_key="test"),
        ).process(job_id)
        assert status.value == "failed"
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 500 and wallet.reserved == 0
    assert len(primary.requests) == 1
    assert not fallback.requests


@pytest.mark.asyncio
async def test_image_fallback_failure_releases_once_and_worker_replay_is_safe(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = api_client
    telegram_id = 910_009
    token = await _login(client, telegram_id)
    quote_id = await _quote(client, token, model_slug="runway-gen4-image")
    created = await client.post(
        "/api/v1/generations",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "image-fallback-failure-replay",
        },
        json={"quote_id": quote_id, "prompt": "A neutral product scene"},
    )
    assert created.status_code == 201
    quoted_price = created.json()["user_credit_price"]
    primary = ImmediateProvider(
        GenerationProviderResult(status="failed", error_code="provider_unavailable"),
        name="runway",
    )
    fallback = ImmediateProvider(
        GenerationProviderResult(status="failed", error_code="provider_timeout"),
        name="google",
    )

    def route_provider(provider_name: str, **_: object) -> ImmediateProvider:
        return fallback if provider_name == "google" else primary

    monkeypatch.setattr("kelbet.services.generation_runner.resolve_provider", route_provider)
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    job_id = queue.pop_all()[0][0]
    async with session_factory() as session, session.begin():
        for key in ("google_image", "image_fallback"):
            flag = await session.get(FeatureFlag, key)
            assert flag is not None
            flag.enabled = True
            flag.payload = {"telegram_ids": [telegram_id]}
    settings = Settings(runway_api_key="test", google_api_key="test")
    storage = app.state.object_storage  # type: ignore[attr-defined]
    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage, settings=settings).process(job_id)
        assert status.value == "failed"
    async with session_factory() as session, session.begin():
        replay = await GenerationRunner(session, storage, settings=settings).process(job_id)
        assert replay.value == "failed"
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        wallet = (await session.execute(select(Wallet))).scalar_one()
        usages = list(
            (
                await session.execute(
                    select(ProviderUsage)
                    .where(ProviderUsage.generation_id == job_id)
                    .order_by(ProviderUsage.created_at)
                )
            )
            .scalars()
            .all()
        )
        assert job.user_credit_price == quoted_price
        assert wallet.balance == 500 and wallet.reserved == 0
        assert [usage.provider for usage in usages] == ["runway", "google"]
    assert len(primary.requests) == len(fallback.requests) == 1
