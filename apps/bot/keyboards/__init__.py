from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(Msg.LANG_KK, Language.KK),
                    callback_data="lang:kk",
                ),
                InlineKeyboardButton(
                    text=t(Msg.LANG_RU, Language.RU),
                    callback_data="lang:ru",
                ),
            ]
        ]
    )


def main_menu_keyboard(lang: Language) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(Msg.MENU_CREATE, lang)),
                KeyboardButton(text=t(Msg.MENU_AI_CHAT, lang)),
            ],
            [
                KeyboardButton(text=t(Msg.MENU_MY_WORKS, lang)),
                KeyboardButton(text=t(Msg.MENU_TARIFFS, lang)),
            ],
            [
                KeyboardButton(text=t(Msg.MENU_PARTNERSHIP, lang)),
                KeyboardButton(text=t(Msg.MENU_PROFILE, lang)),
            ],
        ],
        resize_keyboard=True,
    )
