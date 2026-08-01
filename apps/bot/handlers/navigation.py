from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import MenuText
from apps.bot.keyboards import (
    language_keyboard,
    main_menu_keyboard,
    mini_app_launch_keyboard,
    referral_keyboard,
    support_keyboard,
)
from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t
from kelbet.services.profile import ProfileService
from kelbet.services.referral import ReferralService
from kelbet.services.registration import RegistrationService, UserDTO

router = Router(name="navigation")


async def _registered_user(
    message: Message,
    session: AsyncSession,
) -> UserDTO | None:
    if message.from_user is None:
        return None
    result = await RegistrationService(session).handle_start(
        message.from_user.id,
        message.from_user.username,
    )
    if result.user is not None:
        return result.user
    await message.answer(
        t(Msg.NEED_REGISTER, Language.KK),
        reply_markup=language_keyboard(),
    )
    return None


async def _open_mini_app(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
    *,
    path: str,
    label_key: str,
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
    await message.answer(
        t(Msg.MINI_APP_OPEN, user.language),
        reply_markup=mini_app_launch_keyboard(
            user.language,
            mini_app_url=settings.mini_app_url,
            path=path,
            label_key=label_key,
        ),
    )


@router.message(Command("menu"))
async def on_menu(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    user = await _registered_user(message, session)
    if user is None:
        return
    await state.clear()
    await message.answer(
        t(Msg.MENU_TITLE, user.language),
        reply_markup=main_menu_keyboard(user.language, settings.mini_app_url),
    )


@router.message(Command("create"))
@router.message(MenuText(Msg.MENU_CREATE))
async def on_create(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    await _open_mini_app(
        message,
        session,
        state,
        settings,
        path="create",
        label_key=Msg.MINI_APP_CREATE,
    )


@router.message(Command("video"))
@router.message(MenuText(Msg.MENU_VIDEO))
async def on_video(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    await _open_mini_app(
        message,
        session,
        state,
        settings,
        path="video",
        label_key=Msg.MINI_APP_VIDEO,
    )


@router.message(Command("trends"))
@router.message(MenuText(Msg.MENU_TRENDS))
async def on_trends(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    await _open_mini_app(
        message,
        session,
        state,
        settings,
        path="trends",
        label_key=Msg.MINI_APP_TRENDS,
    )


@router.message(Command("history"))
@router.message(MenuText(Msg.MENU_MY_WORKS))
async def on_history(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    await _open_mini_app(
        message,
        session,
        state,
        settings,
        path="history",
        label_key=Msg.MINI_APP_HISTORY,
    )


@router.message(Command("plans"))
@router.message(MenuText(Msg.MENU_TARIFFS))
async def on_plans(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    await _open_mini_app(
        message,
        session,
        state,
        settings,
        path="plans",
        label_key=Msg.MINI_APP_PLANS,
    )


@router.message(Command("balance"))
@router.message(MenuText(Msg.MENU_BALANCE))
async def on_balance(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    user = await _registered_user(message, session)
    if user is None:
        return
    await state.clear()
    profile = await ProfileService(session).get_profile(user.telegram_id)
    lines = [
        t(Msg.BALANCE_TITLE, user.language),
        t(Msg.BALANCE_TOTAL, user.language, balance=profile.balance),
        t(Msg.BALANCE_RESERVED, user.language, reserved=profile.reserved),
        t(Msg.BALANCE_AVAILABLE, user.language, available=profile.available),
    ]
    reply_markup = None
    if settings.mini_app_url.strip():
        reply_markup = mini_app_launch_keyboard(
            user.language,
            mini_app_url=settings.mini_app_url,
            path="plans",
            label_key=Msg.BALANCE_TOP_UP,
        )
    await message.answer("\n".join(lines), reply_markup=reply_markup)


@router.message(Command("settings"))
async def on_settings(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    user = await _registered_user(message, session)
    if user is None:
        return
    await state.clear()
    await message.answer(
        f"{t(Msg.SETTINGS_TITLE, user.language)}\n{t(Msg.SETTINGS_LANGUAGE, user.language)}",
        reply_markup=language_keyboard(),
    )


@router.message(Command("support", "paysupport"))
async def on_support(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    user = await _registered_user(message, session)
    if user is None:
        return
    await state.clear()
    command = (message.text or "").split(maxsplit=1)[0].split("@", maxsplit=1)[0].lower()
    text_key = Msg.PAY_SUPPORT_TEXT if command == "/paysupport" else Msg.SUPPORT_TEXT
    if not settings.support_username.strip().lstrip("@"):
        await message.answer(t(Msg.SUPPORT_UNAVAILABLE, user.language))
        return
    await message.answer(
        t(text_key, user.language),
        reply_markup=support_keyboard(user.language, settings.support_username),
    )


@router.message(Command("invite"))
@router.message(MenuText(Msg.MENU_INVITE, Msg.MENU_PARTNERSHIP))
async def on_invite(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    user = await _registered_user(message, session)
    if user is None:
        return
    await state.clear()
    summary = await ReferralService(session, settings).get_summary(user.id)
    if not summary.enabled or not summary.link:
        await message.answer(t(Msg.INVITE_COMING_SOON, user.language))
        return
    await message.answer(
        t(
            Msg.INVITE_SUMMARY,
            user.language,
            link=summary.link,
            invited=summary.invited_count,
            pending=summary.pending_rewards_count,
            credited=summary.credited_bonus_credits,
            inviter_bonus=summary.inviter_bonus_credits,
            minimum=summary.minimum_purchase_stars,
            waiting=summary.waiting_period_hours,
        ),
        reply_markup=referral_keyboard(
            user.language,
            link=summary.link,
            mini_app_url=settings.mini_app_url,
        ),
    )
