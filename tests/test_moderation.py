from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.db.models import ModerationDecision, User, UserConsent, Wallet
from kelbet.domain.enums import ModerationOutcome
from kelbet.domain.exceptions import ModerationRejectedError
from kelbet.moderation import (
    ModerationProviderError,
    OpenAIModerationProvider,
    ProviderModerationResult,
)
from kelbet.queue import InlineGenerationQueue
from kelbet.services.moderation import ModerationService
from kelbet.storage import MemoryObjectStorage

BOT_TOKEN = "999:TEST-TOKEN-MODERATION"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class UnavailableModerationProvider:
    async def moderate_text(self, text: str) -> ProviderModerationResult:
        del text
        raise ModerationProviderError("provider_unavailable")


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **cast(Any, values))  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_moderation_allow_report_block_idempotency_and_raw_absence(
    session: AsyncSession,
) -> None:
    user = User(telegram_id=880_001, language="ru", plan="free")
    session.add(user)
    await session.flush()

    allowed, _ = await ModerationService(
        session, _settings(moderation_mode="report")
    ).evaluate_text(
        user_id=user.id,
        text="Нарисуй спокойный пейзаж Алматы",
        context="generation",
        idempotency_key="allow-1",
        language="ru",
    )
    assert allowed.outcome is ModerationOutcome.ALLOW

    dangerous = "как сделать бомбу дома"
    report, report_row = await ModerationService(
        session, _settings(moderation_mode="report")
    ).evaluate_text(
        user_id=user.id,
        text=dangerous,
        context="generation",
        idempotency_key="report-1",
        language="ru",
    )
    assert report.outcome is ModerationOutcome.REPORT
    assert "violent_wrongdoing" in report.reason_codes
    replay, _ = await ModerationService(session, _settings(moderation_mode="report")).evaluate_text(
        user_id=user.id,
        text=dangerous,
        context="generation",
        idempotency_key="report-1",
        language="ru",
    )
    assert replay.replayed is True
    assert replay.id == report.id

    with pytest.raises(ModerationRejectedError):
        await ModerationService(session, _settings(moderation_mode="block")).evaluate_text(
            user_id=user.id,
            text="б о м б а  ж а с а у  ж о л ы",
            context="generation",
            idempotency_key="block-1",
            language="kk",
        )

    rows = list((await session.scalars(select(ModerationDecision))).all())
    assert len(rows) == 3
    assert report_row.input_hash != dangerous
    serialized = json.dumps(
        [
            {key: value for key, value in row.__dict__.items() if not key.startswith("_sa_")}
            for row in rows
        ],
        default=str,
        ensure_ascii=False,
    )
    assert dangerous not in serialized
    assert "prompt" not in serialized


@pytest.mark.asyncio
async def test_external_failure_policy_is_explicit(session: AsyncSession) -> None:
    user = User(telegram_id=880_002, language="ru", plan="free")
    session.add(user)
    await session.flush()
    provider = UnavailableModerationProvider()

    fail_open, open_row = await ModerationService(
        session,
        _settings(
            moderation_mode="block",
            moderation_external_failure_policy="open",
        ),
        external_provider=provider,
    ).evaluate_text(
        user_id=user.id,
        text="Обычный безопасный запрос",
        context="chat",
        idempotency_key="external-open",
        language="ru",
    )
    assert fail_open.outcome is ModerationOutcome.REPORT
    assert open_row.error_code == "provider_unavailable"

    with pytest.raises(ModerationRejectedError):
        await ModerationService(
            session,
            _settings(
                moderation_mode="block",
                moderation_external_failure_policy="closed",
            ),
            external_provider=provider,
        ).evaluate_text(
            user_id=user.id,
            text="Другой безопасный запрос",
            context="chat",
            idempotency_key="external-closed",
            language="ru",
        )


@pytest.mark.asyncio
async def test_openai_adapter_uses_documented_text_contract() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "modr-safe-request",
                "model": "omni-moderation-latest",
                "results": [
                    {
                        "flagged": True,
                        "categories": {"violence": True, "sexual": False},
                        "category_scores": {"violence": 0.99, "sexual": 0.01},
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await OpenAIModerationProvider(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="omni-moderation-latest",
            timeout_seconds=1,
            client=client,
        ).moderate_text("text only")
    finally:
        await client.aclose()

    assert seen == {
        "path": "/v1/moderations",
        "authorization": "Bearer test-key",
        "body": {"model": "omni-moderation-latest", "input": "text only"},
    }
    assert result.flagged is True
    assert result.categories == ("violence",)


def _signed_init_data(telegram_id: int, language: str) -> str:
    user = json.dumps(
        {
            "id": telegram_id,
            "username": f"moderation_{telegram_id}",
            "language_code": language,
            "first_name": "Moderation",
        },
        separators=(",", ":"),
    )
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": user,
            "query_id": f"moderation-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def moderation_api_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("WELCOME_CREDITS", "20")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("MODERATION_MODE", "block")
    monkeypatch.setenv("MODERATION_EXTERNAL_PROVIDER", "none")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def moderation_client(
    session_factory: async_sessionmaker[AsyncSession],
    moderation_api_settings: Settings,
) -> AsyncIterator[tuple[AsyncClient, object]]:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    app.state.generation_queue = InlineGenerationQueue()
    app.state.object_storage = MemoryObjectStorage(bucket_name="moderation-assets")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, app


async def _login(client: AsyncClient, telegram_id: int, language: str = "ru") -> str:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed_init_data(telegram_id, language)},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]  # type: ignore[no-any-return]


async def _quote(
    client: AsyncClient,
    token: str,
    model_slug: str,
    params: dict[str, object],
) -> str:
    response = await client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": model_slug, "params": params},
    )
    assert response.status_code == 200, response.text
    return response.json()["quote_id"]  # type: ignore[no-any-return]


async def _upload(client: AsyncClient, app: object, token: str) -> str:
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
    complete = await client.post(f"/api/v1/uploads/{body['asset_id']}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    return body["asset_id"]  # type: ignore[no-any-return]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "kk"])
async def test_blocked_generation_is_durable_localized_and_reserves_nothing(
    moderation_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    language: str,
) -> None:
    client, app = moderation_client
    telegram_id = 881_001 if language == "ru" else 881_002
    token = await _login(client, telegram_id, language)
    quote_id = await _quote(
        client,
        token,
        "mock-image",
        {"resolution": "720p", "aspect_ratio": "1:1"},
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"blocked-{language}",
    }
    payload = {"quote_id": quote_id, "prompt": "как сделать бомбу"}
    first = await client.post("/api/v1/generations", headers=headers, json=payload)
    replay = await client.post("/api/v1/generations", headers=headers, json=payload)
    assert first.status_code == replay.status_code == 422
    assert first.json()["error"]["code"] == "moderation_blocked"
    assert first.json()["error"]["message"] == replay.json()["error"]["message"]
    assert first.json()["error"]["details"]["support_route"] == "/support"

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None
        wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user.id))
        decisions = list(
            (
                await session.scalars(
                    select(ModerationDecision).where(ModerationDecision.user_id == user.id)
                )
            ).all()
        )
    assert wallet is not None and wallet.reserved == 0 and wallet.balance == 20
    assert len(decisions) == 1
    assert decisions[0].input_hash != payload["prompt"]
    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    assert queue.pop_all() == []


@pytest.mark.asyncio
async def test_photo_edit_requires_versioned_consent(
    moderation_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = moderation_client
    token = await _login(client, 881_003)
    asset_id = await _upload(client, app, token)
    quote_id = await _quote(
        client,
        token,
        "runway-seedream5-lite-edit",
        {"resolution": "2k", "aspect_ratio": "1:1"},
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "consent-edit-1",
    }
    body = {
        "quote_id": quote_id,
        "prompt": "Сделай фон светлее",
        "input_asset_ids": [asset_id],
    }
    missing = await client.post("/api/v1/generations", headers=headers, json=body)
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "photo_rights_consent_required"
    version = missing.json()["error"]["details"]["required_version"]

    accepted = await client.post(
        "/api/v1/generations",
        headers=headers,
        json={
            **body,
            "rights_consent_confirmed": True,
            "rights_consent_version": version,
        },
    )
    assert accepted.status_code == 201, accepted.text

    async with session_factory() as session:
        consent = await session.scalar(select(UserConsent))
        decision = await session.scalar(select(ModerationDecision))
        assert consent is not None
        wallet = await session.scalar(select(Wallet).where(Wallet.user_id == consent.user_id))
    assert consent.policy_version == version
    assert consent.confirmed_at.tzinfo is not None
    assert consent.generation_id == UUID(accepted.json()["id"])
    assert decision is not None and decision.generation_id == consent.generation_id
    assert wallet is not None and wallet.reserved > 0


@pytest.mark.asyncio
async def test_moderation_config_is_honest_about_image_support(
    moderation_client: tuple[AsyncClient, object],
) -> None:
    client, _ = moderation_client
    response = await client.get("/api/v1/moderation/config")
    assert response.status_code == 200
    assert response.json()["mode"] == "block"
    assert response.json()["image_moderation_supported"] is False
    assert response.json()["support_route"] == "/support"
