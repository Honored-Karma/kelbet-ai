from aiogram import Bot
from aiogram.types import BotCommand

from kelbet.domain.enums import Language
from kelbet.i18n import Msg, t


def bot_commands(lang: Language) -> list[BotCommand]:
    return [
        BotCommand(command="start", description=t(Msg.CMD_START, lang)),
        BotCommand(command="menu", description=t(Msg.CMD_MENU, lang)),
        BotCommand(command="create", description=t(Msg.CMD_CREATE, lang)),
        BotCommand(command="video", description=t(Msg.CMD_VIDEO, lang)),
        BotCommand(command="trends", description=t(Msg.CMD_TRENDS, lang)),
        BotCommand(command="chat", description=t(Msg.CMD_CHAT, lang)),
        BotCommand(command="history", description=t(Msg.CMD_HISTORY, lang)),
        BotCommand(command="invite", description=t(Msg.CMD_INVITE, lang)),
        BotCommand(command="balance", description=t(Msg.CMD_BALANCE, lang)),
        BotCommand(command="buy", description=t(Msg.CMD_BUY, lang)),
        BotCommand(command="profile", description=t(Msg.CMD_PROFILE, lang)),
        BotCommand(command="settings", description=t(Msg.CMD_SETTINGS, lang)),
        BotCommand(command="support", description=t(Msg.CMD_SUPPORT, lang)),
    ]


async def configure_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(bot_commands(Language.RU))
    for lang in Language:
        await bot.set_my_commands(bot_commands(lang), language_code=lang.value)
