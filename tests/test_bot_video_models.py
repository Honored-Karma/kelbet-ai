"""Video model picker in the bot.

The picker is the first screen a user sees after tapping "Create video", so the things
worth pinning are the ones that would strand them there: a keyboard that outlives the
catalog behind it, a page button that leads nowhere, callback data Telegram refuses to
deliver, and a price on the button that disagrees with the price at checkout.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message
from apps.bot.handlers.video import (
    CALLBACK_DATA_LIMIT,
    PAGE_SIZE,
    clamp_page,
    model_button_label,
    models_keyboard,
    on_page,
    on_pick,
    on_video,
    page_count,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.catalog.pricing import compute_user_credit_price, credit_price_range
from kelbet.catalog.seed_db import seed_catalog
from kelbet.catalog.seeds import catalog_model_rows
from kelbet.config import Settings
from kelbet.db.models.catalog import FeatureFlag
from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t
from kelbet.services.catalog import CatalogService
from kelbet.services.registration import RegistrationService

MINI_APP = "https://app.kelbet.ai"


async def _register(session: AsyncSession, *, telegram_id: int, language: Language) -> None:
    await RegistrationService(session, Settings(welcome_credits=5)).register_with_language(
        telegram_id=telegram_id,
        username="video_user",
        language=language,
    )


async def _enable_flag(session: AsyncSession, key: str) -> None:
    await session.execute(update(FeatureFlag).where(FeatureFlag.key == key).values(enabled=True))
    await session.flush()


def _message(*, telegram_id: int, text: str | None = "/video") -> MagicMock:
    message = MagicMock()
    message.from_user = MagicMock(id=telegram_id, username="video_user")
    message.text = text
    message.answer = AsyncMock()
    return message


def _callback(*, telegram_id: int, data: str) -> MagicMock:
    # spec=Message keeps the handlers' isinstance check meaningful: they refuse to touch
    # an inaccessible message, and a bare MagicMock would sail past that guard.
    inner = MagicMock(spec=Message)
    inner.answer = AsyncMock()
    inner.edit_reply_markup = AsyncMock()
    inner.reply_markup = None

    callback = MagicMock()
    callback.from_user = MagicMock(id=telegram_id, username="video_user")
    callback.data = data
    callback.message = inner
    callback.answer = AsyncMock()
    return callback


async def _visible_slugs(session: AsyncSession, *, telegram_id: int) -> list[str]:
    models = await CatalogService(session).list_models_for_user(
        language=Language.RU,
        telegram_id=telegram_id,
    )
    return [model.slug for model in models if model.modality.value == "video"]


@pytest.mark.asyncio
async def test_create_video_offers_the_model_list_instead_of_opening_the_studio(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(mini_app_url=MINI_APP)
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await _register(session, telegram_id=7201, language=Language.RU)
        message = _message(telegram_id=7201)
        state = AsyncMock()

        await on_video(message, session, state, settings)

        state.clear.assert_awaited_once()
        args, kwargs = message.answer.await_args
        assert args[0] == t(Msg.VIDEO_MODEL_CHOOSE, Language.RU)
        rows = kwargs["reply_markup"].inline_keyboard
        assert rows, "no models offered"
        # Every model row selects a model; nothing opens the studio blind.
        assert all(button.callback_data.startswith("vmodel:") for row in rows for button in row)


@pytest.mark.asyncio
async def test_the_fal_catalog_stays_hidden_until_its_flag_is_turned_on(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The thirteen fal SKUs ship flag-off because the account is unfunded and no clip
    has been reconciled. Listing them early would sell a route that cannot run."""
    settings = Settings(mini_app_url=MINI_APP)
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await _register(session, telegram_id=7202, language=Language.RU)

        before = await _visible_slugs(session, telegram_id=7202)
        assert not [slug for slug in before if slug.startswith("fal-")]

        await _enable_flag(session, "fal_video")
        after = await _visible_slugs(session, telegram_id=7202)

        revealed = [slug for slug in after if slug.startswith("fal-")]
        assert revealed, "enabling fal_video revealed nothing"
        # The premium band has its own flag and must stay shut.
        assert "fal-seedance-20-video" not in revealed
        assert "fal-kling-o3-4k-video" not in revealed
        assert "fal-kling-30-pro-video" in revealed

        message = _message(telegram_id=7202)
        await on_video(message, session, AsyncMock(), settings)
        _args, kwargs = message.answer.await_args
        labels = [button.text for row in kwargs["reply_markup"].inline_keyboard for button in row]
        assert any("Kling 3.0 Pro" in label for label in labels)


@pytest.mark.asyncio
async def test_paging_covers_the_catalog_without_repeating_a_model(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await _register(session, telegram_id=7203, language=Language.RU)
        await _enable_flag(session, "fal_video")
        await _enable_flag(session, "fal_video_premium")

        models = [
            model
            for model in await CatalogService(session).list_models_for_user(
                language=Language.RU, telegram_id=7203
            )
            if model.modality.value == "video"
            and (model.capabilities.get("ui") or {}).get("operation") == "video"
            and not (model.capabilities.get("ui") or {}).get("hidden_in_production")
        ]
        assert len(models) > PAGE_SIZE, "catalog too small to exercise the pager"

        seen: list[str] = []
        for page in range(page_count(len(models))):
            keyboard = models_keyboard(models, language=Language.RU, page=page)
            picks = [
                button.callback_data.removeprefix("vmodel:pick:")
                for row in keyboard.inline_keyboard
                for button in row
                if button.callback_data.startswith("vmodel:pick:")
            ]
            assert picks, f"page {page} offers no model"
            seen.extend(picks)

        assert len(seen) == len(set(seen)), "a model appears on two pages"
        assert set(seen) == {model.slug for model in models}


@pytest.mark.asyncio
async def test_a_page_button_from_a_shrunken_catalog_still_renders(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An operator turning a flag off between send and tap must not produce an empty
    keyboard with no way back."""
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await _register(session, telegram_id=7204, language=Language.RU)
        callback = _callback(telegram_id=7204, data="vmodel:page:99")

        await on_page(callback, session, Settings(mini_app_url=MINI_APP))

        callback.message.edit_reply_markup.assert_awaited_once()
        _args, kwargs = callback.message.edit_reply_markup.await_args
        assert kwargs["reply_markup"].inline_keyboard
        callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_picking_a_model_deep_links_into_the_studio_with_it_preselected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await _register(session, telegram_id=7205, language=Language.RU)
        await _enable_flag(session, "fal_video")
        callback = _callback(telegram_id=7205, data="vmodel:pick:fal-kling-30-pro-video")

        await on_pick(callback, session, Settings(mini_app_url=MINI_APP))

        _args, kwargs = callback.message.answer.await_args
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        assert button.web_app is not None
        # Without the query parameter the studio would fall back to its own default and
        # discard the choice the user just made.
        assert button.web_app.url == f"{MINI_APP}/video?model=fal-kling-30-pro-video"


@pytest.mark.asyncio
async def test_picking_a_model_its_flag_now_hides_says_so_instead_of_opening(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await _register(session, telegram_id=7206, language=Language.RU)
        # fal_video deliberately left off: the button is from an older message.
        callback = _callback(telegram_id=7206, data="vmodel:pick:fal-kling-30-pro-video")

        await on_pick(callback, session, Settings(mini_app_url=MINI_APP))

        callback.message.answer.assert_not_awaited()
        callback.answer.assert_awaited_once_with(
            t(Msg.VIDEO_MODEL_GONE, Language.RU), show_alert=True
        )


@pytest.mark.asyncio
async def test_an_unconfigured_mini_app_url_reports_itself(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await _register(session, telegram_id=7207, language=Language.KK)
        message = _message(telegram_id=7207)

        await on_video(message, session, AsyncMock(), Settings(mini_app_url=""))

        args, _kwargs = message.answer.await_args
        assert args[0] == t(Msg.MINI_APP_UNAVAILABLE, Language.KK)


def test_callback_data_fits_what_telegram_will_deliver() -> None:
    """Telegram silently drops a button whose callback_data exceeds 64 bytes, so a long
    slug would render an unpressable model."""
    for row in catalog_model_rows():
        if row["modality"] != "video":
            continue
        payload = f"vmodel:pick:{row['slug']}"
        assert len(payload.encode()) <= CALLBACK_DATA_LIMIT, (
            f"{row['slug']} needs {len(payload.encode())} bytes of callback data"
        )


def test_button_price_range_matches_what_the_quote_will_charge() -> None:
    """The button advertises a range; the quote charges a point inside it. If the range
    were computed differently the user would meet a price they were never shown."""
    for row in catalog_model_rows():
        if row["modality"] != "video":
            continue
        capabilities = row["capabilities"]
        rules = row["pricing_rules"]
        assert isinstance(capabilities, dict)
        low, high = credit_price_range(
            row["user_credit_price"], capabilities=capabilities, pricing_rules=rules
        )
        assert low <= high

        for resolution in capabilities.get("resolutions") or [None]:
            for duration in capabilities.get("durations_sec") or [None]:
                params: dict[str, object] = {}
                if resolution is not None:
                    params["resolution"] = resolution
                if duration is not None:
                    params["duration_sec"] = int(duration)
                quoted = compute_user_credit_price(
                    row["user_credit_price"], params=params, pricing_rules=rules
                )
                assert low <= quoted <= high, (
                    f"{row['slug']} quotes {quoted} outside the advertised {low}-{high}"
                )


def test_page_arithmetic_never_offers_an_empty_page() -> None:
    assert page_count(0) == 1
    assert page_count(1) == 1
    assert page_count(PAGE_SIZE) == 1
    assert page_count(PAGE_SIZE + 1) == 2

    assert clamp_page(-5, 20) == 0
    assert clamp_page(99, 20) == page_count(20) - 1
    assert clamp_page(1, 0) == 0


@pytest.mark.asyncio
async def test_button_label_shows_a_single_price_when_the_model_has_one(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A model with one duration and one resolution must not advertise "50-50"."""
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        flags = (await session.execute(select(FeatureFlag))).scalars().all()
        assert flags, "catalog seeded no feature flags"

        models = await CatalogService(session).list_models_for_user(
            language=Language.RU, telegram_id=7208, include_disabled=True
        )
        single = [
            model
            for model in models
            if len(model.capabilities.get("durations_sec") or [1]) == 1
            and len(model.capabilities.get("resolutions") or [1]) == 1
            and not model.pricing_rules
        ]
        for model in single:
            assert "-" not in model_button_label(model, Language.RU).rsplit("·", 1)[-1]
