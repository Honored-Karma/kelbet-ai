"""Background worker entry — ARQ image / text / video / maintain queues."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import cast
from uuid import UUID

from aiogram import Bot
from arq import cron
from arq.connections import RedisSettings

from kelbet.config import Settings, get_settings
from kelbet.db.session import build_session_factory
from kelbet.observability import configure_json_logging
from kelbet.services.generation_runner import GenerationRunner
from kelbet.services.notification import (
    NotificationDispatcher,
    TelegramGenerationReadySender,
)
from kelbet.services.stuck_sweeper import StuckSweeper
from kelbet.storage import build_object_storage

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, object]) -> None:
    settings = get_settings()
    configure_json_logging(settings.log_level)
    ctx["session_factory"] = build_session_factory(settings)
    ctx["storage"] = build_object_storage(settings)
    ctx["settings"] = settings
    if settings.bot_token:
        ctx["bot"] = Bot(token=settings.bot_token)
    logger.info("worker_arq_started")


async def shutdown(ctx: dict[str, object]) -> None:
    # ARQ stops dequeue on SIGTERM and waits for in-flight jobs (job_timeout).
    # Stuck submitting/running jobs are recovered by MaintainWorkerSettings.sweep.
    logger.info("worker_arq_stopping_graceful")
    bot = ctx.get("bot")
    if isinstance(bot, Bot):
        await bot.session.close()


async def process_generation(ctx: dict[str, object], generation_id: str) -> str:
    session_factory = ctx["session_factory"]
    storage = ctx["storage"]
    settings = ctx.get("settings") or get_settings()
    async with session_factory() as session, session.begin():  # type: ignore[operator]
        status = await GenerationRunner(
            session,
            storage,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        ).process(UUID(generation_id))
        return status.value


async def poll_due_generations(ctx: dict[str, object]) -> int:
    session_factory = ctx["session_factory"]
    storage = ctx["storage"]
    settings = ctx.get("settings") or get_settings()
    async with session_factory() as session, session.begin():  # type: ignore[operator]
        statuses = await GenerationRunner(
            session,
            storage,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        ).poll_due(limit=50)
        return len(statuses)


async def sweep_stuck_generations(ctx: dict[str, object]) -> int:
    session_factory = ctx["session_factory"]
    settings = ctx.get("settings") or get_settings()
    async with session_factory() as session, session.begin():  # type: ignore[operator]
        swept = await StuckSweeper(session, settings).sweep(limit=50)  # type: ignore[arg-type]
        return len(swept)


async def dispatch_generation_notifications(ctx: dict[str, object]) -> int:
    bot = ctx.get("bot")
    if not isinstance(bot, Bot):
        return 0
    session_factory = ctx["session_factory"]
    settings = cast(Settings, ctx.get("settings") or get_settings())
    sender = TelegramGenerationReadySender(
        bot,
        settings.mini_app_url,
    )
    async with session_factory() as session, session.begin():  # type: ignore[operator]
        return await NotificationDispatcher(
            session,
            sender,
            settings=settings,
        ).dispatch_due()


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


def _job_timeout() -> int:
    return get_settings().worker_job_timeout_seconds


class ImageWorkerSettings:
    """Run with: arq apps.worker.main.ImageWorkerSettings"""

    functions = [process_generation]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:image"
    max_jobs = 4
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings


class TextWorkerSettings:
    """Run with: arq apps.worker.main.TextWorkerSettings"""

    functions = [process_generation]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:text"
    max_jobs = 8
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings


class VideoWorkerSettings:
    """Run with: arq apps.worker.main.VideoWorkerSettings — low concurrency."""

    functions = [process_generation]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:video"
    max_jobs = 2
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings


class MaintainWorkerSettings:
    """Poll due jobs + sweep stuck generations for recovery after worker death."""

    functions = [
        poll_due_generations,
        sweep_stuck_generations,
        dispatch_generation_notifications,
    ]
    cron_jobs = [
        cron(poll_due_generations, second=set(range(0, 60, 5))),
        cron(sweep_stuck_generations, second={15, 45}),
        cron(
            dispatch_generation_notifications,
            second={5, 15, 25, 35, 45, 55},
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:maintain"
    max_jobs = 1
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings


# Back-compat alias
WorkerSettings = ImageWorkerSettings


async def _idle_stub() -> None:
    settings = get_settings()
    configure_json_logging(settings.log_level)
    logger.info(
        "worker_stub_started env=%s backend=%s",
        settings.app_env,
        settings.generation_queue_backend,
    )
    stop = asyncio.Event()

    def _request_stop(*_: object) -> None:
        stop.set()

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _request_stop)
    else:
        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
    await stop.wait()
    logger.info("worker_stub_stopped")


def main() -> None:
    settings = get_settings()
    if settings.generation_queue_backend.strip().lower() == "arq":
        configure_json_logging(settings.log_level)
        logger.error(
            "Start ARQ with ImageWorkerSettings, TextWorkerSettings, "
            "VideoWorkerSettings, and MaintainWorkerSettings"
        )
        asyncio.run(_idle_stub())
        return
    asyncio.run(_idle_stub())


if __name__ == "__main__":
    main()
