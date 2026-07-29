import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from apps.bot.handlers import build_root_router
from apps.bot.middlewares import DbSessionMiddleware
from kelbet.config import get_settings
from kelbet.db.session import build_session_factory


async def run_bot() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    if not settings.bot_token:
        msg = "BOT_TOKEN is not set"
        raise RuntimeError(msg)

    redis = Redis.from_url(settings.redis_url)
    storage = RedisStorage(redis=redis)
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=storage)

    session_factory = build_session_factory(settings)
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.include_router(build_root_router())

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await redis.close()
        await redis.connection_pool.disconnect()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
