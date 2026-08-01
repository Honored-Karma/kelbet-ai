from aiogram.filters import BaseFilter
from aiogram.types import Message

from kelbet.i18n import normalize_button_text, texts_for


class MenuText(BaseFilter):
    """Матчит текст reply-кнопки по всем локализациям ключей.

    Сравнение идёт по нормализованному тексту (без эмодзи, пунктуации
    и регистра), чтобы кнопки со старых клавиатур в чатах пользователей
    продолжали работать после смены оформления подписей.
    """

    def __init__(self, *keys: str) -> None:
        self._normalized = {normalize_button_text(text) for key in keys for text in texts_for(key)}

    async def __call__(self, message: Message) -> bool:
        if message.text is None:
            return False
        return normalize_button_text(message.text) in self._normalized
