import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from apps.bot.commands import configure_bot_commands
from apps.bot.handlers import build_root_router
from apps.bot.middlewares import (
    CorrelationIdMiddleware,
    DbSessionMiddleware,
    TelegramUpdateInboxMiddleware,
)
from kelbet.chat.factory import build_chat_provider
from kelbet.config import get_settings
from kelbet.db.session import build_session_factory
from kelbet.observability import initialize_observability


async def run_bot() -> None:
    settings = get_settings()
    initialize_observability(settings, component="bot")

    if not settings.bot_token:
        msg = "BOT_TOKEN is not set"
        raise RuntimeError(msg)

    redis = Redis.from_url(settings.redis_url)
    storage = RedisStorage(redis=redis)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    session_factory = build_session_factory(settings)
    chat_provider = build_chat_provider(settings)

    dp["settings"] = settings
    dp["chat_provider"] = chat_provider
    dp.update.outer_middleware(CorrelationIdMiddleware())
    dp.update.outer_middleware(TelegramUpdateInboxMiddleware(session_factory, settings))
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.include_router(build_root_router())

    try:
        await configure_bot_commands(bot)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await redis.close()
        await redis.connection_pool.disconnect()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
