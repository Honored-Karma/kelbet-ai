"""Server-side generation template catalog, snapshots and compositors."""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import imageio_ffmpeg
import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.db.models.catalog import GenerationTemplate, PriceQuote
from kelbet.db.models.generation import GenerationJob
from kelbet.providers.base import GenerationOutput
from kelbet.queue import InlineGenerationQueue
from kelbet.services.template_compositor import TemplateCompositor
from kelbet.storage import MemoryObjectStorage

BOT_TOKEN = "999:TEST-TOKEN-TEMPLATES"


def _signed_init_data(telegram_id: int) -> str:
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": json.dumps(
                {
                    "id": telegram_id,
                    "username": f"template_{telegram_id}",
                    "language_code": "ru",
                    "first_name": "Template",
                },
                separators=(",", ":"),
            ),
            "query_id": f"q-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def template_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("QUOTE_TTL_SECONDS", "600")
    monkeypatch.setenv("WELCOME_CREDITS", "20")
    monkeypatch.setenv("GENERATION_QUEUE_BACKEND", "inline")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def template_client(
    session_factory: async_sessionmaker[AsyncSession],
    template_settings: Settings,
) -> AsyncIterator[tuple[AsyncClient, object]]:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    app.state.generation_queue = InlineGenerationQueue()
    app.state.object_storage = MemoryObjectStorage(bucket_name="kelbet-assets")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, app


async def _login(client: AsyncClient, telegram_id: int) -> str:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed_init_data(telegram_id)},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_catalog_has_one_ordered_ru_kk_source_and_kind_filter(
    template_client: tuple[AsyncClient, object],
) -> None:
    client, _app = template_client
    token = await _login(client, 720001)
    headers = {"Authorization": f"Bearer {token}"}
    ru = await client.get("/api/v1/catalog/templates?lang=ru", headers=headers)
    kk = await client.get("/api/v1/catalog/templates?lang=kk", headers=headers)
    video = await client.get("/api/v1/catalog/templates?lang=kk&kind=video", headers=headers)
    assert ru.status_code == kk.status_code == video.status_code == 200
    ru_items = ru.json()["items"]
    kk_items = kk.json()["items"]
    assert len(ru_items) == len(kk_items) == 11
    assert [item["slug"] for item in ru_items] == [item["slug"] for item in kk_items]
    assert len([item for item in ru_items if item["kind"] == "image"]) == 6
    assert len(video.json()["items"]) == 5
    assert all(item["localization"]["name"] for item in ru_items + kk_items)
    assert all(item["prompt_preset"] for item in ru_items + kk_items)
    assert [item["display_order"] for item in ru_items] == sorted(
        item["display_order"] for item in ru_items
    )


@pytest.mark.asyncio
async def test_quote_rejects_unknown_incompatible_and_uncontrolled_inputs(
    template_client: tuple[AsyncClient, object],
) -> None:
    client, _app = template_client
    token = await _login(client, 720002)
    headers = {"Authorization": f"Bearer {token}"}
    catalog = await client.get("/api/v1/catalog/templates?lang=ru", headers=headers)
    product = next(
        item for item in catalog.json()["items"] if item["slug"] == "marketplace-product"
    )
    required_inputs = {
        "headline": "Керамическая чашка",
        "price": "12 900 ₸",
        "contact": "+7 700 000 00 00",
    }
    valid = await client.post(
        "/api/v1/wallet/quote",
        headers=headers,
        json={
            "model_slug": "mock-image",
            "params": {"resolution": "720p", "aspect_ratio": "1:1"},
            "template_id": product["id"],
            "template_inputs": required_inputs,
        },
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["template_slug"] == "marketplace-product"
    assert valid.json()["template_inputs"] == required_inputs

    unknown_field = await client.post(
        "/api/v1/wallet/quote",
        headers=headers,
        json={
            "model_slug": "mock-image",
            "params": {"resolution": "720p", "aspect_ratio": "1:1"},
            "template_id": product["id"],
            "template_inputs": {**required_inputs, "font_url": "https://invalid.test/font"},
        },
    )
    assert unknown_field.status_code == 422

    incompatible = await client.post(
        "/api/v1/wallet/quote",
        headers=headers,
        json={
            "model_slug": "mock-text",
            "params": {},
            "template_id": product["id"],
            "template_inputs": required_inputs,
        },
    )
    assert incompatible.status_code == 422

    unknown = await client.post(
        "/api/v1/wallet/quote",
        headers=headers,
        json={
            "model_slug": "mock-image",
            "params": {"resolution": "720p", "aspect_ratio": "1:1"},
            "template_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        },
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_disabled_template_is_hidden_and_rejected_for_new_quote(
    template_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _app = template_client
    token = await _login(client, 720004)
    headers = {"Authorization": f"Bearer {token}"}
    before = await client.get("/api/v1/catalog/templates?lang=ru", headers=headers)
    cafe = next(item for item in before.json()["items"] if item["slug"] == "cafe-promo")
    async with session_factory() as session, session.begin():
        template = (
            await session.execute(
                select(GenerationTemplate).where(GenerationTemplate.slug == "cafe-promo")
            )
        ).scalar_one()
        template.enabled = False

    after = await client.get("/api/v1/catalog/templates?lang=ru", headers=headers)
    assert "cafe-promo" not in {item["slug"] for item in after.json()["items"]}
    quote = await client.post(
        "/api/v1/wallet/quote",
        headers=headers,
        json={
            "model_slug": "mock-image",
            "params": {"resolution": "720p", "aspect_ratio": "1:1"},
            "template_id": cafe["id"],
        },
    )
    assert quote.status_code == 404


@pytest.mark.asyncio
async def test_generation_keeps_immutable_template_snapshot_and_reuses_draft(
    template_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _app = template_client
    token = await _login(client, 720003)
    headers = {"Authorization": f"Bearer {token}"}
    templates = (
        await client.get("/api/v1/catalog/templates?lang=ru&kind=image", headers=headers)
    ).json()["items"]
    cafe = next(item for item in templates if item["slug"] == "cafe-promo")
    product = next(item for item in templates if item["slug"] == "marketplace-product")
    quote = await client.post(
        "/api/v1/wallet/quote",
        headers=headers,
        json={
            "model_slug": "mock-image",
            "params": {"resolution": "720p", "aspect_ratio": "1:1"},
            "template_id": cafe["id"],
            "template_inputs": {},
        },
    )
    assert quote.status_code == 200, quote.text
    created = await client.post(
        "/api/v1/generations",
        headers={
            **headers,
            "Idempotency-Key": "template-snapshot-create",
        },
        json={
            "quote_id": quote.json()["quote_id"],
            "prompt": cafe["prompt_preset"],
            "template_id": cafe["id"],
            "template_inputs": {},
        },
    )
    assert created.status_code == 201, created.text
    generation_id = created.json()["id"]
    idempotency_conflict = await client.post(
        "/api/v1/generations",
        headers={
            **headers,
            "Idempotency-Key": "template-snapshot-create",
        },
        json={
            "quote_id": quote.json()["quote_id"],
            "prompt": cafe["prompt_preset"],
            "template_id": product["id"],
            "template_inputs": {
                "headline": "Other",
                "price": "1 ₸",
                "contact": "Other",
            },
        },
    )
    assert idempotency_conflict.status_code == 409

    async with session_factory() as session, session.begin():
        stored_quote = (await session.execute(select(PriceQuote))).scalar_one()
        job = (await session.execute(select(GenerationJob))).scalar_one()
        template = (
            await session.execute(
                select(GenerationTemplate).where(GenerationTemplate.slug == "cafe-promo")
            )
        ).scalar_one()
        original_name = job.template_snapshot["localization"]["ru"]["name"]
        assert stored_quote.template_snapshot == job.template_snapshot
        assert job.template_slug == "cafe-promo"
        template.localization = {
            **template.localization,
            "ru": {"name": "Изменено позже", "description": "Новая редакция"},
        }

    draft = await client.get(f"/api/v1/generations/{generation_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    assert draft.json()["template_id"] == cafe["id"]
    assert draft.json()["template_slug"] == "cafe-promo"
    assert draft.json()["template_version"] == 1
    async with session_factory() as session:
        job = (await session.execute(select(GenerationJob))).scalar_one()
        assert job.template_snapshot["localization"]["ru"]["name"] == original_name


@pytest.mark.asyncio
async def test_controlled_image_and_video_compositors(tmp_path: Path) -> None:
    compositor = TemplateCompositor()
    font_path = (
        Path(__file__).parents[1]
        / "packages"
        / "kelbet"
        / "assets"
        / "fonts"
        / "NotoSans-Variable.ttf"
    )
    font = ImageFont.truetype(str(font_path), size=36)
    missing_glyph = bytes(font.getmask("\u0378"))
    for glyph in "ӘҒҚҢӨҰҮҺІәғқңөұүһі":
        assert bytes(font.getmask(glyph)) != missing_glyph
    image_buffer = BytesIO()
    Image.new("RGB", (640, 640), (235, 238, 242)).save(image_buffer, format="PNG")
    image_result = await compositor.compose(
        GenerationOutput(content_type="image/png", data=image_buffer.getvalue()),
        compositor="product_card_v1",
        inputs={
            "headline": "Шағын бизнес өнімі",
            "body": "Қазақстанда жасалған",
            "price": "12 900 ₸",
            "contact": "+7 700 000 00 00",
        },
        aspect_ratio="1:1",
    )
    assert image_result.content_type == "image/png"
    rendered_image = Image.open(BytesIO(image_result.data)).convert("RGB")
    assert rendered_image.getpixel((100, 560)) != (235, 238, 242)

    executable = imageio_ffmpeg.get_ffmpeg_exe()
    source_path = tmp_path / "source.mp4"
    await asyncio.to_thread(
        subprocess.run,
        [
            executable,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=180x320:d=0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(source_path),
        ],
        check=True,
        timeout=30,
    )
    video_result = await compositor.compose(
        GenerationOutput(content_type="video/mp4", data=source_path.read_bytes()),
        compositor="toi_invite_v1",
        inputs={
            "headline": "Айдана & Әли",
            "body": "Тойымызға шақырамыз",
            "date": "12.09.2026 · 18:00",
            "contact": "Алматы",
        },
        aspect_ratio="9:16",
    )
    assert video_result.content_type == "video/mp4"
    assert len(video_result.data) > 1_000
    composed_path = tmp_path / "composed.mp4"
    composed_path.write_bytes(video_result.data)
    await asyncio.to_thread(
        subprocess.run,
        [
            executable,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(composed_path),
            "-f",
            "null",
            "-",
        ],
        check=True,
        timeout=30,
    )
