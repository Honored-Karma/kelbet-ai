from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import MenuText
from kelbet.domain.enums import Language, Plan
from kelbet.domain.exceptions import UserNotFoundError
from kelbet.i18n import Msg, t
from kelbet.services.profile import ProfileService

router = Router(name="profile")


@router.message(Command("profile"))
@router.message(MenuText(Msg.MENU_PROFILE))
async def on_profile(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return
    await state.clear()

    service = ProfileService(session)
    try:
        profile = await service.get_profile(message.from_user.id)
    except UserNotFoundError:
        await message.answer(t(Msg.START_CHOOSE_LANG, Language.KK))
        return

    lang = profile.language
    username = profile.username or t(Msg.PROFILE_NO_USERNAME, lang)
    plan_label = t(Msg.PLAN_FREE, lang) if profile.plan == Plan.FREE else profile.plan.value
    language_label = t(Msg.LANG_RU, lang) if lang == Language.RU else t(Msg.LANG_KK, lang)

    lines = [
        t(Msg.PROFILE_TITLE, lang),
        t(Msg.PROFILE_TELEGRAM_ID, lang, telegram_id=profile.telegram_id),
        t(Msg.PROFILE_USERNAME, lang, username=username),
        t(Msg.PROFILE_LANGUAGE, lang, language=language_label),
        t(Msg.PROFILE_BALANCE, lang, balance=profile.balance),
        t(Msg.PROFILE_PLAN, lang, plan=plan_label),
    ]
    await message.answer("\n".join(lines))
