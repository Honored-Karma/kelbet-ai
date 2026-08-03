"""Catalog + quote API integration tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.db.models.catalog import CatalogModel, FeatureFlag

BOT_TOKEN = "999:TEST-TOKEN-CATALOG"


def _user_json(*, telegram_id: int = 888001, language_code: str = "ru") -> str:
    return json.dumps(
        {
            "id": telegram_id,
            "username": "catalog_user",
            "language_code": language_code,
            "first_name": "Cat",
        },
        separators=(",", ":"),
    )


def _signed_init_data(*, telegram_id: int = 888001, language_code: str = "ru") -> str:
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": _user_json(telegram_id=telegram_id, language_code=language_code),
            "query_id": f"q-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def catalog_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("QUOTE_TTL_SECONDS", "600")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    catalog_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)

    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _login(client: AsyncClient, telegram_id: int = 888001) -> str:
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed_init_data(telegram_id=telegram_id)},
    )
    assert auth.status_code == 200, auth.text
    return auth.json()["access_token"]  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_catalog_lists_enabled_localized_models(api_client: AsyncClient) -> None:
    token = await _login(api_client)
    response = await api_client.get(
        "/api/v1/catalog/models",
        headers={"Authorization": f"Bearer {token}"},
        params={"lang": "ru"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    slugs = [item["slug"] for item in items]
    assert "mock-text" in slugs
    assert "mock-image" in slugs
    assert "runway-gen4-image" in slugs
    assert "runway-seedream5-lite-image" in slugs
    assert "runway-seedream5-pro-edit" in slugs
    assert "runway-magnific-image-upscale" in slugs
    assert "runway-gemini-omni-video-fast" in slugs
    assert "runway-gen45-video-quality" in slugs
    assert "google-veo31-lite-video-fallback" in slugs
    assert "runway-gen3-video" not in slugs
    assert "legacy-disabled" not in slugs
    mock_image = next(item for item in items if item["slug"] == "mock-image")
    assert mock_image["localization"]["name"] == "Изображение (Mock)"
    assert mock_image["user_credit_price"] == 5
    image_models = [item for item in items if item["modality"] == "image"]
    simple_defaults = [
        item["slug"]
        for item in image_models
        if item["capabilities"].get("ui", {}).get("simple_default")
    ]
    assert simple_defaults == ["runway-seedream5-lite-image"]
    assert mock_image["capabilities"]["ui"]["hidden_in_production"] is True
    edit = next(item for item in items if item["slug"] == "runway-seedream5-pro-edit")
    assert edit["modality"] == "image_edit"
    assert edit["input_requirements"]["source_image"] == "required"
    assert edit["input_requirements"]["max_input_assets"] == 10
    assert edit["capabilities"]["fallback"]["provider_model_id"] == ("gemini-3.1-flash-image")
    assert edit["capabilities"]["fallback"]["supported_modalities"] == [
        "image",
        "image_edit",
    ]
    upscale = next(item for item in items if item["slug"] == "runway-magnific-image-upscale")
    assert upscale["modality"] == "upscale"
    assert upscale["capabilities"]["scale_factors"] == [2]
    assert "fallback" not in upscale["capabilities"]
    video = next(item for item in items if item["slug"] == "runway-gemini-omni-video-fast")
    assert video["capabilities"]["durations_sec"] == [4, 8]
    assert video["capabilities"]["fallback"]["provider"] == "google"
    assert video["input_requirements"]["source_image"] == "optional"
    veo = next(item for item in items if item["slug"] == "google-veo31-lite-video-fallback")
    assert veo["localization"]["name"] == "Google Veo 3.1 Lite"
    assert veo["capabilities"]["durations_sec"] == [4, 6, 8]
    assert veo["capabilities"]["ui"]["hidden_in_production"] is False


@pytest.mark.asyncio
async def test_feature_flag_hides_runway_models(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        flag = (
            await session.execute(select(FeatureFlag).where(FeatureFlag.key == "runway_media"))
        ).scalar_one()
        flag.enabled = False

    token = await _login(api_client, telegram_id=888002)
    response = await api_client.get(
        "/api/v1/catalog/models",
        headers={"Authorization": f"Bearer {token}"},
    )
    slugs = [item["slug"] for item in response.json()["items"]]
    assert "runway-gen4-image" not in slugs
    assert "runway-seedream5-lite-edit" not in slugs
    assert "runway-magnific-image-upscale" not in slugs
    assert "mock-image" in slugs


@pytest.mark.asyncio
async def test_quote_uses_db_price_and_multipliers(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    token = await _login(api_client, telegram_id=888003)
    quote = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": "mock-image", "params": {"resolution": "1080p", "aspect_ratio": "1:1"}},
    )
    assert quote.status_code == 200, quote.text
    body = quote.json()
    assert body["user_credit_price"] == 8  # 5 * 3/2 ceil = 8
    assert body["currency"] == "credits"
    assert "quote_id" in body

    async with session_factory() as session, session.begin():
        model = (
            await session.execute(select(CatalogModel).where(CatalogModel.slug == "mock-image"))
        ).scalar_one()
        model.user_credit_price = 10

    quote2 = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": "mock-image", "params": {"resolution": "720p"}},
    )
    assert quote2.status_code == 200
    assert quote2.json()["user_credit_price"] == 10

    quality = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model_slug": "runway-seedream5-pro-image",
            "params": {"resolution": "2k", "aspect_ratio": "9:16"},
        },
    )
    assert quality.status_code == 200, quality.text
    # 13 base credits * 9/5 for 2k, ceil -> 24. 2k costs $0.09 vs $0.05 at 1k.
    assert quality.json()["user_credit_price"] == 24

    quality_auto = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model_slug": "runway-seedream5-pro-image",
            "params": {"resolution": "auto_2k", "aspect_ratio": "9:16"},
        },
    )
    assert quality_auto.status_code == 200, quality_auto.text
    # auto_2k resolves to the same pixel budget as 2k: 13 * 9/5, ceil -> 24.
    assert quality_auto.json()["user_credit_price"] == 24

    upscale = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": "runway-magnific-image-upscale", "params": {}},
    )
    assert upscale.status_code == 200, upscale.text
    # Magnific 2x costs $0.25, i.e. 63 credits at $0.004 each. Was 60 ($0.24).
    assert upscale.json()["user_credit_price"] == 63
    assert upscale.json()["params"]["scale_factor"] == 2

    video = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model_slug": "runway-gemini-omni-video-fast",
            "params": {
                "resolution": "720p",
                "aspect_ratio": "9:16",
                "duration_sec": 8,
            },
        },
    )
    assert video.status_code == 200, video.text
    assert video.json()["user_credit_price"] == 200

    veo = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model_slug": "google-veo31-lite-video-fallback",
            "params": {
                "resolution": "720p",
                "aspect_ratio": "9:16",
                "duration_sec": 6,
            },
        },
    )
    assert veo.status_code == 200, veo.text
    assert veo.json()["user_credit_price"] == 75

    unsupported_video_seed = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model_slug": "runway-gen45-video-quality",
            "params": {"seed": 42},
        },
    )
    assert unsupported_video_seed.status_code == 422


@pytest.mark.asyncio
async def test_wallet_balance_endpoint(api_client: AsyncClient, catalog_settings: Settings) -> None:
    token = await _login(api_client, telegram_id=888004)
    response = await api_client.get(
        "/api/v1/wallet",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    # The freshly registered wallet holds exactly the configured welcome bonus.
    assert body["balance"] == catalog_settings.welcome_credits
    assert body["reserved"] == 0
    assert body["available"] == catalog_settings.welcome_credits


@pytest.mark.asyncio
async def test_invalid_quote_params(api_client: AsyncClient) -> None:
    token = await _login(api_client, telegram_id=888005)
    response = await api_client.post(
        "/api/v1/wallet/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_slug": "mock-image", "params": {"resolution": "4k"}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_quote_params"


@pytest.mark.asyncio
async def test_kk_localization(api_client: AsyncClient) -> None:
    token = await _login(api_client, telegram_id=888006)
    response = await api_client.get(
        "/api/v1/catalog/models/mock-text",
        headers={"Authorization": f"Bearer {token}"},
        params={"lang": "kk"},
    )
    assert response.status_code == 200
    assert response.json()["localization"]["name"] == "Мәтін (Mock)"
