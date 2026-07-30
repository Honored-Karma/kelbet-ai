from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.keyboards import language_keyboard, main_menu_keyboard
from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t
from kelbet.services.registration import RegistrationService

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    await state.clear()

    service = RegistrationService(session)
    result = await service.handle_start(message.from_user.id, message.from_user.username)

    if result.needs_language:
        await message.answer(
            t(Msg.START_CHOOSE_LANG, Language.KK),
            reply_markup=language_keyboard(),
        )
        return

    assert result.user is not None
    lang = result.user.language
    await message.answer(
        t(Msg.START_WELCOME_BACK, lang),
        reply_markup=main_menu_keyboard(lang, settings.mini_app_url),
    )


@router.callback_query(F.data.in_({"lang:ru", "lang:kk"}))
async def on_language_chosen(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        return

    language = Language.RU if callback.data == "lang:ru" else Language.KK
    await state.clear()
    service = RegistrationService(session)
    user, credit = await service.register_with_language(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        language=language,
    )

    if credit.applied:
        text = t(Msg.START_WELCOME, language, credits=settings.welcome_credits)
    else:
        text = t(Msg.START_WELCOME_BACK, language)

    await callback.message.answer(
        text,
        reply_markup=main_menu_keyboard(user.language, settings.mini_app_url),
    )
    await callback.answer(t(Msg.LANG_SET, language))
