from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import MenuText
from apps.bot.keyboards import (
    chat_after_answer_keyboard,
    chat_waiting_keyboard,
    language_keyboard,
    main_menu_keyboard,
)
from apps.bot.states import ChatStates
from kelbet.chat import ChatProvider
from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.domain.exceptions import (
    ChatMessageTooLongError,
    ChatProviderError,
    InsufficientCreditsError,
    UserNotFoundError,
)
from kelbet.i18n import Msg, t
from kelbet.services.chat import ChatService
from kelbet.services.registration import RegistrationService

router = Router(name="chat")

_MAIN_MENU_FILTER = MenuText(Msg.CHAT_MAIN_MENU, Msg.MENU_TITLE)


async def _resolve_lang(session: AsyncSession, telegram_id: int, username: str | None) -> Language:
    service = RegistrationService(session)
    result = await service.handle_start(telegram_id, username)
    if result.user is None:
        return Language.KK
    return result.user.language


@router.message(Command("chat"))
@router.message(MenuText(Msg.MENU_AI_CHAT))
async def on_ai_chat_entry(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    reg = RegistrationService(session)
    start = await reg.handle_start(message.from_user.id, message.from_user.username)
    if start.user is None:
        await message.answer(
            t(Msg.CHAT_NEED_REGISTER, Language.KK),
            reply_markup=language_keyboard(),
        )
        return

    lang = start.user.language
    cost = settings.chat_credit_cost
    if start.user.balance < cost:
        await message.answer(
            t(Msg.CHAT_INSUFFICIENT, lang, cost=cost, balance=start.user.balance),
            reply_markup=main_menu_keyboard(lang, settings.mini_app_url),
        )
        return

    await state.set_state(ChatStates.waiting_message)
    await message.answer(
        t(Msg.CHAT_PROMPT, lang),
        reply_markup=chat_waiting_keyboard(lang),
    )


@router.message(MenuText(Msg.CHAT_ASK_AGAIN))
async def on_chat_ask_again(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    reg = RegistrationService(session)
    start = await reg.handle_start(message.from_user.id, message.from_user.username)
    if start.user is None:
        await message.answer(
            t(Msg.CHAT_NEED_REGISTER, Language.KK),
            reply_markup=language_keyboard(),
        )
        return

    lang = start.user.language
    cost = settings.chat_credit_cost
    if start.user.balance < cost:
        await state.clear()
        await message.answer(
            t(Msg.CHAT_INSUFFICIENT, lang, cost=cost, balance=start.user.balance),
            reply_markup=main_menu_keyboard(lang, settings.mini_app_url),
        )
        return

    await state.set_state(ChatStates.waiting_message)
    await message.answer(
        t(Msg.CHAT_PROMPT, lang),
        reply_markup=chat_waiting_keyboard(lang),
    )


@router.message(ChatStates.waiting_message, MenuText(Msg.CHAT_CANCEL))
async def on_chat_cancel(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(session, message.from_user.id, message.from_user.username)
    await state.clear()
    await message.answer(
        t(Msg.CHAT_CANCELLED, lang),
        reply_markup=main_menu_keyboard(lang, settings.mini_app_url),
    )


@router.message(ChatStates.waiting_message, _MAIN_MENU_FILTER)
async def on_chat_main_menu(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(session, message.from_user.id, message.from_user.username)
    await state.clear()
    await message.answer(
        t(Msg.MENU_TITLE, lang),
        reply_markup=main_menu_keyboard(lang, settings.mini_app_url),
    )


@router.message(_MAIN_MENU_FILTER)
async def on_main_menu_button(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    lang = await _resolve_lang(session, message.from_user.id, message.from_user.username)
    await state.clear()
    await message.answer(
        t(Msg.MENU_TITLE, lang),
        reply_markup=main_menu_keyboard(lang, settings.mini_app_url),
    )


@router.message(ChatStates.waiting_message, F.text)
async def on_chat_message(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    chat_provider: ChatProvider,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    cfg = settings
    lang = await _resolve_lang(session, message.from_user.id, message.from_user.username)
    text = message.text or ""

    if not text.strip():
        await message.answer(
            t(Msg.CHAT_EMPTY, lang),
            reply_markup=chat_waiting_keyboard(lang),
        )
        return

    request_id = f"{message.from_user.id}:{message.message_id}"
    service = ChatService(session, chat_provider, settings=cfg)

    try:
        result = await service.ask(
            telegram_id=message.from_user.id,
            message=text,
            request_id=request_id,
        )
    except UserNotFoundError:
        await state.clear()
        await message.answer(
            t(Msg.CHAT_NEED_REGISTER, Language.KK),
            reply_markup=language_keyboard(),
        )
        return
    except InsufficientCreditsError:
        reg = RegistrationService(session)
        start = await reg.handle_start(message.from_user.id, message.from_user.username)
        balance = start.user.balance if start.user is not None else 0
        await state.clear()
        await message.answer(
            t(Msg.CHAT_INSUFFICIENT, lang, cost=cfg.chat_credit_cost, balance=balance),
            reply_markup=main_menu_keyboard(lang, settings.mini_app_url),
        )
        return
    except ChatMessageTooLongError:
        await message.answer(
            t(Msg.CHAT_TOO_LONG, lang, max_chars=cfg.chat_max_input_chars),
            reply_markup=chat_waiting_keyboard(lang),
        )
        return
    except ChatProviderError:
        await message.answer(
            t(Msg.CHAT_PROVIDER_ERROR, lang),
            reply_markup=chat_waiting_keyboard(lang),
        )
        return

    if not result.answer:
        await message.answer(
            t(Msg.CHAT_PROVIDER_ERROR, lang),
            reply_markup=chat_waiting_keyboard(lang),
        )
        return

    await state.clear()
    # AI-ответ — недоверенный текст: отключаем HTML-парсинг, чтобы "<" не ломал отправку.
    await message.answer(result.answer, parse_mode=None)
    await message.answer(
        t(Msg.CHAT_BALANCE_LEFT, result.language, balance=result.balance),
        reply_markup=chat_after_answer_keyboard(result.language),
    )
