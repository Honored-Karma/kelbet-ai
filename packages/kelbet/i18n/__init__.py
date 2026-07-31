from kelbet.domain.enums import Language
from kelbet.i18n import kk, ru
from kelbet.i18n.keys import Msg

_CATALOGS: dict[Language, dict[str, str]] = {
    Language.RU: ru.TEXTS,
    Language.KK: kk.TEXTS,
}


def t(key: str, lang: Language, **kwargs: object) -> str:
    catalog = _CATALOGS.get(lang, kk.TEXTS)
    template = catalog.get(key) or kk.TEXTS.get(key) or key
    if kwargs:
        return template.format(**kwargs)
    return template


def texts_for(key: str) -> list[str]:
    """All localized variants of a key (for ReplyKeyboard routing)."""
    values: list[str] = []
    seen: set[str] = set()
    for catalog in _CATALOGS.values():
        value = catalog.get(key)
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def normalize_button_text(text: str) -> str:
    """Канонизирует подпись кнопки: без эмодзи и пунктуации, регистронезависимо.

    Reply-клавиатуры остаются в чатах пользователей навсегда, поэтому нажатия
    со старых клавиатур должны матчиться даже после смены оформления подписей
    (например, добавления эмодзи).
    """
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text)
    return " ".join(cleaned.split()).casefold()


__all__ = ["Msg", "t", "texts_for", "normalize_button_text", "Language"]
