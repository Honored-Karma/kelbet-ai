from urllib.parse import urlencode

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
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


def mini_app_page_url(base_url: str, path: str) -> str:
    """Join the Mini App origin with a page path.

    `path` may carry a query string ("video?model=..."), which is how the video model
    picker preselects a route.
    """
    return f"{base_url.strip().rstrip('/')}/{path.strip().lstrip('/')}"


def _mini_app_button(
    *,
    text: str,
    base_url: str,
    path: str,
) -> KeyboardButton:
    if not base_url.strip():
        return KeyboardButton(text=text)
    return KeyboardButton(
        text=text,
        web_app=WebAppInfo(url=mini_app_page_url(base_url, path)),
    )


def main_menu_keyboard(lang: Language, mini_app_url: str = "") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                _mini_app_button(
                    text=t(Msg.MENU_CREATE, lang),
                    base_url=mini_app_url,
                    path="create",
                ),
                _mini_app_button(
                    text=t(Msg.MENU_VIDEO, lang),
                    base_url=mini_app_url,
                    path="video",
                ),
            ],
            [
                _mini_app_button(
                    text=t(Msg.MENU_TRENDS, lang),
                    base_url=mini_app_url,
                    path="trends",
                ),
                _mini_app_button(
                    text=t(Msg.MENU_MY_WORKS, lang),
                    base_url=mini_app_url,
                    path="history",
                ),
            ],
            [
                KeyboardButton(text=t(Msg.MENU_AI_CHAT, lang)),
                KeyboardButton(text=t(Msg.MENU_BALANCE, lang)),
            ],
            [
                KeyboardButton(text=t(Msg.MENU_PROFILE, lang)),
                KeyboardButton(text=t(Msg.MENU_INVITE, lang)),
            ],
        ],
        resize_keyboard=True,
    )


def mini_app_launch_keyboard(
    lang: Language,
    *,
    mini_app_url: str,
    path: str,
    label_key: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(label_key, lang),
                    web_app=WebAppInfo(url=mini_app_page_url(mini_app_url, path)),
                )
            ]
        ]
    )


def support_keyboard(lang: Language, support_username: str) -> InlineKeyboardMarkup:
    username = support_username.strip().lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(Msg.SUPPORT_OPEN, lang),
                    url=f"https://t.me/{username}",
                )
            ]
        ]
    )


def referral_keyboard(
    lang: Language,
    *,
    link: str,
    mini_app_url: str,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=t(Msg.INVITE_SHARE, lang),
                url=f"https://t.me/share/url?{urlencode({'url': link})}",
            )
        ]
    ]
    if mini_app_url.strip():
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(Msg.INVITE_OPEN, lang),
                    web_app=WebAppInfo(url=mini_app_page_url(mini_app_url, "invite")),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_waiting_keyboard(lang: Language) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(Msg.CHAT_CANCEL, lang)),
                KeyboardButton(text=t(Msg.CHAT_MAIN_MENU, lang)),
            ],
        ],
        resize_keyboard=True,
    )


def chat_after_answer_keyboard(lang: Language) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(Msg.CHAT_ASK_AGAIN, lang)),
                KeyboardButton(text=t(Msg.CHAT_MAIN_MENU, lang)),
            ],
        ],
        resize_keyboard=True,
    )
