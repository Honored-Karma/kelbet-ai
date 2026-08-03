"""Stage G: Mini App text generations (mock + OpenRouter via reserve/capture)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.db.models.generation import ProviderUsage
from kelbet.db.models.wallet import Wallet
from kelbet.providers.openrouter import OpenRouterTextProvider
from kelbet.queue import InlineGenerationQueue
from kelbet.services.generation_runner import GenerationRunner
from kelbet.storage import MemoryObjectStorage
from kelbet.storage.keys import build_output_object_key
from kelbet.storage.validation import extension_for_mime

BOT_TOKEN = "999:TEST-TOKEN-TEXT"


def _user_json(*, telegram_id: int) -> str:
    return json.dumps(
        {
            "id": telegram_id,
            "username": f"text_{telegram_id}",
            "language_code": "ru",
            "first_name": "Text",
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
def text_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("QUOTE_TTL_SECONDS", "600")
    monkeypatch.setenv("WELCOME_CREDITS", "20")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.setenv("GENERATION_QUEUE_BACKEND", "inline")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    text_settings: Settings,
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
    response = await client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": model_slug, "params": {}},
    )
    assert response.status_code == 200, response.text
    return response.json()["quote_id"]  # type: ignore[no-any-return]


async def _drain(
    app: object,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    provider: object | None = None,
) -> list[str]:
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    storage = app.state.object_storage  # type: ignore[attr-defined]
    statuses: list[str] = []
    for generation_id, _modality in queue.pop_all():
        async with session_factory() as session, session.begin():
            runner = GenerationRunner(
                session,
                storage,
                provider=provider,  # type: ignore[arg-type]
            )
            status = await runner.process(generation_id)
            statuses.append(status.value)
    return statuses


def test_text_plain_output_extension() -> None:
    assert extension_for_mime("text/plain") == "txt"
    assert extension_for_mime("text/plain; charset=utf-8") == "txt"
    key = build_output_object_key(
        user_id=uuid4(),
        asset_id=uuid4(),
        content_type="text/plain; charset=utf-8",
    )
    assert key.endswith(".txt")


@pytest.mark.asyncio
async def test_mock_text_generation_capture(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 810001)
    quote_id = await _quote(client, token, model_slug="mock-text")

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "text-happy"},
        json={"quote_id": quote_id, "prompt": "Қалайсың?"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["modality"] == "text"
    assert created.json()["user_credit_price"] == 1
    gen_id = created.json()["id"]

    statuses = await _drain(app, session_factory)
    assert statuses == ["succeeded"]

    got = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "succeeded"
    assert len(got.json()["output_asset_ids"]) == 1

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 19
        assert wallet.reserved == 0


@pytest.mark.asyncio
async def test_mock_text_fail_releases(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 810002)
    quote_id = await _quote(client, token, model_slug="mock-text")
    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "text-fail"},
        json={"quote_id": quote_id, "prompt": "fail"},
    )
    assert created.status_code == 201
    statuses = await _drain(app, session_factory)
    assert statuses == ["failed"]

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 20
        assert wallet.reserved == 0


@pytest.mark.asyncio
async def test_openrouter_text_generation_reserve_capture(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 810003)
    quote_id = await _quote(client, token, model_slug="openrouter-gpt-4o-mini")

    created = await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "or-text-1"},
        json={"quote_id": quote_id, "prompt": "Напиши одно слово: ок"},
    )
    assert created.status_code == 201, created.text
    gen_id = created.json()["id"]
    assert created.json()["model_slug"] == "openrouter-gpt-4o-mini"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["model"] == "openai/gpt-4o-mini"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ок"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 1},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        provider = OpenRouterTextProvider.from_settings(
            get_settings(),
            client=http_client,
        )
        statuses = await _drain(app, session_factory, provider=provider)

    assert statuses == ["succeeded"]

    got = await client.get(
        f"/api/v1/generations/{gen_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert got.json()["status"] == "succeeded"
    assert len(got.json()["output_asset_ids"]) == 1

    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        # 20 welcome credits less the 2 that openrouter-gpt-4o-mini costs in the catalog.
        assert wallet.balance == 18
        assert wallet.reserved == 0
        usage = (await session.execute(select(ProviderUsage))).scalar_one()
        assert usage.provider == "openrouter"
        assert usage.tokens_in == 8
        assert usage.tokens_out == 1


@pytest.mark.asyncio
async def test_openrouter_provider_error_no_capture(
    api_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = api_client
    token = await _login(client, 810004)
    quote_id = await _quote(client, token, model_slug="openrouter-gpt-4o-mini")
    await client.post(
        "/api/v1/generations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "or-fail"},
        json={"quote_id": quote_id, "prompt": "boom"},
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        provider = OpenRouterTextProvider.from_settings(
            get_settings(),
            client=http_client,
        )
        statuses = await _drain(app, session_factory, provider=provider)

    assert statuses == ["failed"]
    async with session_factory() as session, session.begin():
        wallet = (await session.execute(select(Wallet))).scalar_one()
        assert wallet.balance == 20
        assert wallet.reserved == 0
