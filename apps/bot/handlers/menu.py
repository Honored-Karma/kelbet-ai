from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import MenuText
from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t
from kelbet.services.registration import RegistrationService

router = Router(name="menu")

# Резервный ответ, если раздел ещё не подключён в navigation-роутере
# (он зарегистрирован раньше и перехватывает эти кнопки, когда доступен).
_STUB_KEYS = (
    Msg.MENU_CREATE,
    Msg.MENU_MY_WORKS,
    Msg.MENU_TARIFFS,
    Msg.MENU_PARTNERSHIP,
)


@router.message(MenuText(*_STUB_KEYS))
async def on_stub_menu(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    service = RegistrationService(session)
    result = await service.handle_start(message.from_user.id, message.from_user.username)
    lang = result.user.language if result.user is not None else Language.KK
    await message.answer(t(Msg.COMING_SOON, lang))
