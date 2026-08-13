from unittest.mock import AsyncMock, MagicMock

import pytest
from apps.bot.commands import bot_commands, configure_bot_commands
from apps.bot.filters import MenuText
from apps.bot.handlers.navigation import on_balance, on_create, on_trends
from apps.bot.keyboards import main_menu_keyboard
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.i18n import Msg, normalize_button_text, t
from kelbet.services.registration import RegistrationService


async def _register(
    session: AsyncSession,
    *,
    telegram_id: int,
    language: Language,
) -> None:
    await RegistrationService(session, Settings(welcome_credits=5)).register_with_language(
        telegram_id=telegram_id,
        username="navigation_user",
        language=language,
    )


def _message(*, telegram_id: int, text: str | None) -> MagicMock:
    message = MagicMock()
    message.from_user = MagicMock(id=telegram_id, username="navigation_user")
    message.text = text
    message.answer = AsyncMock()
    return message


def test_normalize_button_text_ignores_emoji_punctuation_and_case() -> None:
    assert normalize_button_text("🎨 Создать изображение") == "создать изображение"
    assert normalize_button_text("💬 AI-чат") == normalize_button_text("AI-чат")
    assert normalize_button_text("  Сурет   жасау ") == "сурет жасау"


@pytest.mark.asyncio
async def test_menu_buttons_match_legacy_labels_without_emoji() -> None:
    """Кнопки со старых reply-клавиатур (до добавления эмодзи) должны работать."""
    create_filter = MenuText(Msg.MENU_CREATE)

    for text in (
        t(Msg.MENU_CREATE, Language.RU),
        t(Msg.MENU_CREATE, Language.KK),
        "Создать изображение",
        "Сурет жасау",
    ):
        assert await create_filter(_message(telegram_id=1, text=text)) is True

    assert await create_filter(_message(telegram_id=1, text="Создать видео")) is False
    assert await create_filter(_message(telegram_id=1, text=None)) is False


def test_main_menu_uses_mini_app_links_when_configured() -> None:
    keyboard = main_menu_keyboard(Language.RU, "https://app.kelbet.ai/")

    create = keyboard.keyboard[0][0]
    video = keyboard.keyboard[0][1]
    trends = keyboard.keyboard[1][0]
    history = keyboard.keyboard[1][1]
    balance = keyboard.keyboard[2][1]

    assert create.web_app is not None
    assert create.web_app.url == "https://app.kelbet.ai/create"
    assert video.web_app is not None
    assert video.web_app.url == "https://app.kelbet.ai/video"
    assert trends.web_app is not None
    assert trends.web_app.url == "https://app.kelbet.ai/trends"
    assert history.web_app is not None
    assert history.web_app.url == "https://app.kelbet.ai/history"
    assert balance.text == t(Msg.MENU_BALANCE, Language.RU)
    assert balance.web_app is None


def test_main_menu_falls_back_to_regular_buttons_without_url() -> None:
    keyboard = main_menu_keyboard(Language.KK)

    assert keyboard.keyboard[0][0].web_app is None
    assert keyboard.keyboard[0][1].web_app is None
    assert keyboard.keyboard[1][0].web_app is None
    assert keyboard.keyboard[1][1].web_app is None
    assert keyboard.keyboard[2][1].text == t(Msg.MENU_BALANCE, Language.KK)


def test_bot_commands_are_localized() -> None:
    russian = bot_commands(Language.RU)
    kazakh = bot_commands(Language.KK)

    assert [command.command for command in russian] == [
        "start",
        "menu",
        "create",
        "video",
        "trends",
        "chat",
        "history",
        "invite",
        "balance",
        "buy",
        "profile",
        "settings",
        "support",
        "paysupport",
        "terms",
    ]
    assert russian[2].description == t(Msg.CMD_CREATE, Language.RU)
    assert kazakh[2].description == t(Msg.CMD_CREATE, Language.KK)
    assert russian[7].description == t(Msg.CMD_INVITE, Language.RU)
    assert kazakh[7].description == t(Msg.CMD_INVITE, Language.KK)
    assert russian[-2].description == t(Msg.CMD_PAY_SUPPORT, Language.RU)
    assert kazakh[-1].description == t(Msg.CMD_TERMS, Language.KK)


@pytest.mark.asyncio
async def test_configure_bot_commands_sets_default_and_languages() -> None:
    bot = MagicMock()
    bot.set_my_commands = AsyncMock()

    await configure_bot_commands(bot)

    assert bot.set_my_commands.await_count == 3
    assert bot.set_my_commands.await_args_list[0].kwargs == {}
    assert bot.set_my_commands.await_args_list[1].kwargs == {"language_code": "ru"}
    assert bot.set_my_commands.await_args_list[2].kwargs == {"language_code": "kk"}


@pytest.mark.asyncio
async def test_create_command_returns_mini_app_link(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(mini_app_url="https://app.kelbet.ai")

    async with session_factory() as session, session.begin():
        await _register(session, telegram_id=6101, language=Language.RU)
        message = _message(telegram_id=6101, text="/create")
        state = AsyncMock()

        await on_create(message, session, state, settings)

        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()
        args, kwargs = message.answer.await_args
        assert args[0] == t(Msg.MINI_APP_OPEN, Language.RU)
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        assert button.web_app.url == "https://app.kelbet.ai/create"


@pytest.mark.asyncio
async def test_create_command_prompts_registration(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(mini_app_url="https://app.kelbet.ai")

    async with session_factory() as session, session.begin():
        message = _message(telegram_id=6102, text="/create")
        state = AsyncMock()

        await on_create(message, session, state, settings)

        state.clear.assert_not_awaited()
        args, _kwargs = message.answer.await_args
        assert args[0] == t(Msg.NEED_REGISTER, Language.KK)


@pytest.mark.asyncio
async def test_trends_command_returns_trend_lab_link(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(mini_app_url="https://app.kelbet.ai")

    async with session_factory() as session, session.begin():
        await _register(session, telegram_id=6105, language=Language.RU)
        message = _message(telegram_id=6105, text="/trends")
        state = AsyncMock()

        await on_trends(message, session, state, settings)

        state.clear.assert_awaited_once()
        args, kwargs = message.answer.await_args
        assert args[0] == t(Msg.MINI_APP_OPEN, Language.RU)
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        assert button.web_app.url == "https://app.kelbet.ai/trends"


@pytest.mark.asyncio
async def test_balance_command_shows_reserved_and_available(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(mini_app_url="")

    async with session_factory() as session, session.begin():
        await _register(session, telegram_id=6103, language=Language.KK)
        message = _message(telegram_id=6103, text="/balance")
        state = AsyncMock()

        await on_balance(message, session, state, settings)

        state.clear.assert_awaited_once()
        args, kwargs = message.answer.await_args
        assert t(Msg.BALANCE_TITLE, Language.KK) in args[0]
        assert t(Msg.BALANCE_TOTAL, Language.KK, balance=5) in args[0]
        assert t(Msg.BALANCE_RESERVED, Language.KK, reserved=0) in args[0]
        assert t(Msg.BALANCE_AVAILABLE, Language.KK, available=5) in args[0]
        assert kwargs["reply_markup"] is None
