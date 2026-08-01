from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.keyboards import language_keyboard, main_menu_keyboard
from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t
from kelbet.services.registration import RegistrationService

router = Router(name="start")


def referral_code_from_start(args: str | None) -> str | None:
    value = (args or "").strip()
    if not value.startswith("ref_"):
        return None
    code = value[4:]
    if not 8 <= len(code) <= 32 or any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        for char in code
    ):
        return None
    return code


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    command: CommandObject,
) -> None:
    if message.from_user is None:
        return
    service = RegistrationService(session)
    result = await service.handle_start(message.from_user.id, message.from_user.username)

    state_data = await state.get_data()
    pending_code = state_data.get("pending_referral_code")
    await state.clear()
    if result.user is None:
        first_touch = pending_code if isinstance(pending_code, str) else None
        first_touch = first_touch or referral_code_from_start(command.args)
        if first_touch:
            await state.update_data(pending_referral_code=first_touch)

    # Язык выбирается при каждом /start; приветствие приходит после выбора.
    prompt_lang = result.user.language if result.user is not None else Language.KK
    await message.answer(
        t(Msg.START_CHOOSE_LANG, prompt_lang),
        reply_markup=language_keyboard(),
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
    state_data = await state.get_data()
    referral_code = state_data.get("pending_referral_code")
    await state.clear()
    service = RegistrationService(session)
    user, credit = await service.register_with_language(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        language=language,
        referral_code=referral_code if isinstance(referral_code, str) else None,
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
