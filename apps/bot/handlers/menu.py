from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t, texts_for
from kelbet.services.registration import RegistrationService

router = Router(name="menu")

_STUB_KEYS = (
    Msg.MENU_CREATE,
    Msg.MENU_AI_CHAT,
    Msg.MENU_MY_WORKS,
    Msg.MENU_TARIFFS,
    Msg.MENU_PARTNERSHIP,
)

_STUB_TEXTS = [text for key in _STUB_KEYS for text in texts_for(key)]


@router.message(F.text.in_(_STUB_TEXTS))
async def on_stub_menu(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    service = RegistrationService(session)
    result = await service.handle_start(message.from_user.id, message.from_user.username)
    lang = result.user.language if result.user is not None else Language.KK
    await message.answer(t(Msg.COMING_SOON, lang))
