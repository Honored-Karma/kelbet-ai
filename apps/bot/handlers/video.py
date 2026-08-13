"""Video model picker.

"Create video" used to open the Mini App straight away, which meant the model choice
was buried three taps deep behind an expandable "precise settings" panel. The catalog
now carries nineteen video routes, so the choice is the first thing asked instead of
the last thing found.

The bot deliberately does not collect the prompt, the photo or the aspect ratio. That
UI already exists in the Mini App, and a second implementation in chat would be a
second set of validation rules to keep in step with the quote endpoint. Picking a
model here just deep-links into the studio with that model preselected, so there is
one generation path, not two.

Only models the user can actually reach are listed: `list_models_for_user` applies the
per-model feature flag and its telegram_id allowlist, so a canary model stays hidden
rather than failing at the quote.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import MenuText
from apps.bot.keyboards import (
    language_keyboard,
    main_menu_keyboard,
    mini_app_page_url,
)
from kelbet.catalog.pricing import credit_price_range
from kelbet.config import Settings
from kelbet.domain.enums import Language, Modality
from kelbet.i18n import Msg, t
from kelbet.services.catalog import CatalogModelDTO, CatalogService
from kelbet.services.registration import RegistrationService, UserDTO

router = Router(name="video")

#: Rows per page. Telegram renders more without complaint, but a keyboard taller than
#: the viewport hides the pager the user needs to reach the rest of the catalog.
PAGE_SIZE = 8

_PICK_PREFIX = "vmodel:pick:"
_PAGE_PREFIX = "vmodel:page:"
#: Telegram rejects callback_data over 64 bytes. Slugs are ASCII and the longest in the
#: catalog leaves comfortable headroom under the prefix, which `tests` pins.
CALLBACK_DATA_LIMIT = 64


async def _registered_user(message: Message, session: AsyncSession) -> UserDTO | None:
    if message.from_user is None:
        return None
    result = await RegistrationService(session).handle_start(
        message.from_user.id,
        message.from_user.username,
    )
    if result.user is not None:
        return result.user
    # Same contract as the navigation router: an unregistered user is asked to pick a
    # language rather than silently ignored.
    await message.answer(
        t(Msg.NEED_REGISTER, Language.KK),
        reply_markup=language_keyboard(),
    )
    return None


async def _video_models(
    session: AsyncSession,
    *,
    language: Language,
    telegram_id: int,
) -> list[CatalogModelDTO]:
    models = await CatalogService(session).list_models_for_user(
        language=language,
        telegram_id=telegram_id,
    )
    visible = [
        model
        for model in models
        if model.modality is Modality.VIDEO
        and (model.capabilities.get("ui") or {}).get("operation") == "video"
        and not (model.capabilities.get("ui") or {}).get("hidden_in_production")
    ]
    return sorted(visible, key=lambda model: model.display_order)


def model_button_label(model: CatalogModelDTO, language: Language) -> str:
    """`Kling 3.0 Pro · 140-280 credits`, matching how the quote will actually price."""
    low, high = credit_price_range(
        model.user_credit_price,
        capabilities=model.capabilities,
        pricing_rules=model.pricing_rules,
    )
    amount = str(low) if low == high else f"{low}-{high}"
    return t(Msg.VIDEO_MODEL_BUTTON, language, name=model.localization.name, credits=amount)


def page_count(total: int) -> int:
    if total <= 0:
        return 1
    return (total + PAGE_SIZE - 1) // PAGE_SIZE


def clamp_page(page: int, total: int) -> int:
    """Keep a stale callback from an older message inside the current catalog.

    The catalog can shrink between the keyboard being sent and a button being pressed —
    an operator turning a flag off is enough — and an out-of-range page would render an
    empty keyboard with no way back.
    """
    return max(0, min(page, page_count(total) - 1))


def models_keyboard(
    models: list[CatalogModelDTO],
    *,
    language: Language,
    page: int,
) -> InlineKeyboardMarkup:
    total_pages = page_count(len(models))
    page = clamp_page(page, len(models))
    start = page * PAGE_SIZE
    rows = [
        [
            InlineKeyboardButton(
                text=model_button_label(model, language),
                callback_data=f"{_PICK_PREFIX}{model.slug}",
            )
        ]
        for model in models[start : start + PAGE_SIZE]
    ]

    if total_pages > 1:
        pager: list[InlineKeyboardButton] = []
        if page > 0:
            pager.append(
                InlineKeyboardButton(
                    text=t(Msg.VIDEO_MODEL_PREV, language),
                    callback_data=f"{_PAGE_PREFIX}{page - 1}",
                )
            )
        pager.append(
            InlineKeyboardButton(
                text=t(
                    Msg.VIDEO_MODEL_PAGE,
                    language,
                    page=page + 1,
                    total=total_pages,
                ),
                # Telegram requires callback_data on every button; re-selecting the
                # current page is the cheapest no-op.
                callback_data=f"{_PAGE_PREFIX}{page}",
            )
        )
        if page < total_pages - 1:
            pager.append(
                InlineKeyboardButton(
                    text=t(Msg.VIDEO_MODEL_NEXT, language),
                    callback_data=f"{_PAGE_PREFIX}{page + 1}",
                )
            )
        rows.append(pager)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def studio_keyboard(
    model: CatalogModelDTO,
    *,
    language: Language,
    mini_app_url: str,
) -> InlineKeyboardMarkup:
    """Open the studio with this model already chosen.

    `model=<slug>` is what the Mini App reads to preselect; without it the studio would
    fall back to its own default and quietly discard the choice just made.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(Msg.VIDEO_MODEL_OPEN, language),
                    web_app=WebAppInfo(
                        url=mini_app_page_url(mini_app_url, f"video?model={model.slug}")
                    ),
                )
            ]
        ]
    )


@router.message(Command("video"))
@router.message(MenuText(Msg.MENU_VIDEO))
async def on_video(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    user = await _registered_user(message, session)
    if user is None:
        return
    await state.clear()
    if not settings.mini_app_url.strip():
        await message.answer(
            t(Msg.MINI_APP_UNAVAILABLE, user.language),
            reply_markup=main_menu_keyboard(user.language, settings.mini_app_url),
        )
        return

    models = await _video_models(session, language=user.language, telegram_id=user.telegram_id)
    if not models:
        await message.answer(
            t(Msg.VIDEO_MODEL_EMPTY, user.language),
            reply_markup=main_menu_keyboard(user.language, settings.mini_app_url),
        )
        return

    await message.answer(
        t(Msg.VIDEO_MODEL_CHOOSE, user.language),
        reply_markup=models_keyboard(models, language=user.language, page=0),
    )


@router.callback_query(F.data.startswith(_PAGE_PREFIX))
async def on_page(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    result = await RegistrationService(session).handle_start(
        callback.from_user.id,
        callback.from_user.username,
    )
    user = result.user
    if user is None:
        await callback.answer()
        return

    raw = (callback.data or "").removeprefix(_PAGE_PREFIX)
    try:
        page = int(raw)
    except ValueError:
        await callback.answer()
        return

    models = await _video_models(session, language=user.language, telegram_id=user.telegram_id)
    if not models:
        await callback.answer(t(Msg.VIDEO_MODEL_EMPTY, user.language), show_alert=True)
        return

    keyboard = models_keyboard(models, language=user.language, page=page)
    # Telegram rejects an edit that changes nothing, which is exactly what tapping the
    # current-page label does. Answering the callback is enough to clear the spinner.
    if callback.message.reply_markup != keyboard:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith(_PICK_PREFIX))
async def on_pick(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    result = await RegistrationService(session).handle_start(
        callback.from_user.id,
        callback.from_user.username,
    )
    user = result.user
    if user is None:
        await callback.answer()
        return

    slug = (callback.data or "").removeprefix(_PICK_PREFIX)
    models = await _video_models(session, language=user.language, telegram_id=user.telegram_id)
    model = next((item for item in models if item.slug == slug), None)
    if model is None:
        # The keyboard outlived the model: a flag was turned off, or the SKU retired.
        await callback.answer(t(Msg.VIDEO_MODEL_GONE, user.language), show_alert=True)
        return
    if not settings.mini_app_url.strip():
        await callback.answer(t(Msg.MINI_APP_UNAVAILABLE, user.language), show_alert=True)
        return

    low, high = credit_price_range(
        model.user_credit_price,
        capabilities=model.capabilities,
        pricing_rules=model.pricing_rules,
    )
    await callback.message.answer(
        t(
            Msg.VIDEO_MODEL_PICKED,
            user.language,
            name=model.localization.name,
            description=model.localization.description,
            credits=str(low) if low == high else f"{low}-{high}",
        ),
        reply_markup=studio_keyboard(
            model,
            language=user.language,
            mini_app_url=settings.mini_app_url,
        ),
    )
    await callback.answer()
