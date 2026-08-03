"""Background worker entry — ARQ image / text / video / maintain queues."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from time import monotonic
from typing import cast
from uuid import UUID

from aiogram import Bot
from arq import cron
from arq.connections import RedisSettings

from kelbet.config import Settings, get_settings
from kelbet.db.session import build_session_factory
from kelbet.observability import correlation_context, get_metrics, initialize_observability
from kelbet.payments.gateway import AiogramStarsGateway
from kelbet.repositories.generation import GenerationRepository
from kelbet.services.generation_runner import GenerationRunner
from kelbet.services.notification import (
    NotificationDispatcher,
    TelegramGenerationReadySender,
)
from kelbet.services.payment_reconciliation import run_star_reconciliation
from kelbet.services.payment_refund import process_due_refund
from kelbet.services.referral import process_due_referral_rewards
from kelbet.services.reservation_sweeper import ReservationSweeper
from kelbet.services.stuck_sweeper import StuckSweeper
from kelbet.services.subscription import process_due_subscriptions
from kelbet.storage import build_object_storage

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, object]) -> None:
    settings = get_settings()
    initialize_observability(settings, component="worker")
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
    started = monotonic()
    outcome = "failed"
    queue = "other"
    try:
        async with session_factory() as session, session.begin():  # type: ignore[operator]
            generation_uuid = UUID(generation_id)
            job = await GenerationRepository(session).get_by_id(generation_uuid)
            queue = job.modality if job is not None else "other"
            correlation_id = str(job.correlation_id) if job is not None else generation_id
            with correlation_context(correlation_id):
                result = await GenerationRunner(
                    session,
                    storage,  # type: ignore[arg-type]
                    settings=settings,  # type: ignore[arg-type]
                ).process(generation_uuid)
            outcome = "succeeded"
            return result.value
    finally:
        _record_worker_metrics("process_generation", queue, outcome, started)


async def poll_due_generations(ctx: dict[str, object]) -> int:
    session_factory = ctx["session_factory"]
    storage = ctx["storage"]
    settings = ctx.get("settings") or get_settings()
    started = monotonic()
    outcome = "failed"
    try:
        async with session_factory() as session, session.begin():  # type: ignore[operator]
            statuses = await GenerationRunner(
                session,
                storage,  # type: ignore[arg-type]
                settings=settings,  # type: ignore[arg-type]
            ).poll_due(limit=50)
            outcome = "succeeded" if statuses else "empty"
            return len(statuses)
    finally:
        _record_worker_metrics("poll_due_generations", "maintain", outcome, started)


async def sweep_stuck_generations(ctx: dict[str, object]) -> int:
    session_factory = ctx["session_factory"]
    settings = ctx.get("settings") or get_settings()
    started = monotonic()
    outcome = "failed"
    try:
        async with session_factory() as session, session.begin():  # type: ignore[operator]
            swept = await StuckSweeper(session, settings).sweep(limit=50)  # type: ignore[arg-type]
            outcome = "succeeded" if swept else "empty"
            return len(swept)
    finally:
        _record_worker_metrics("sweep_stuck_generations", "maintain", outcome, started)


async def sweep_expired_reservations(ctx: dict[str, object]) -> int:
    session_factory = ctx["session_factory"]
    started = monotonic()
    outcome = "failed"
    try:
        async with session_factory() as session, session.begin():  # type: ignore[operator]
            expired = await ReservationSweeper(session).sweep(limit=100)
            outcome = "succeeded" if expired else "empty"
            return len(expired)
    finally:
        _record_worker_metrics("sweep_expired_reservations", "maintain", outcome, started)


async def dispatch_generation_notifications(ctx: dict[str, object]) -> int:
    started = monotonic()
    outcome = "failed"
    bot = ctx.get("bot")
    if not isinstance(bot, Bot):
        _record_worker_metrics("dispatch_generation_notifications", "maintain", "skipped", started)
        return 0
    session_factory = ctx["session_factory"]
    settings = cast(Settings, ctx.get("settings") or get_settings())
    sender = TelegramGenerationReadySender(
        bot,
        settings.mini_app_url,
    )
    try:
        async with session_factory() as session, session.begin():  # type: ignore[operator]
            count = await NotificationDispatcher(
                session,
                sender,
                settings=settings,
            ).dispatch_due()
            outcome = "succeeded" if count else "empty"
            return count
    finally:
        _record_worker_metrics("dispatch_generation_notifications", "maintain", outcome, started)


async def process_star_refund(ctx: dict[str, object]) -> int:
    started = monotonic()
    outcome = "failed"
    settings = cast(Settings, ctx.get("settings") or get_settings())
    bot = ctx.get("bot")
    if not settings.stars_refunds_enabled or not isinstance(bot, Bot):
        _record_worker_metrics("process_star_refund", "maintain", "skipped", started)
        return 0
    try:
        count = await process_due_refund(
            ctx["session_factory"],  # type: ignore[arg-type]
            AiogramStarsGateway(bot),
            settings,
        )
        outcome = "succeeded" if count else "empty"
        return count
    finally:
        _record_worker_metrics("process_star_refund", "maintain", outcome, started)


async def reconcile_star_payments(ctx: dict[str, object]) -> int:
    started = monotonic()
    outcome = "failed"
    settings = cast(Settings, ctx.get("settings") or get_settings())
    bot = ctx.get("bot")
    if not settings.stars_reconciliation_enabled or not isinstance(bot, Bot):
        _record_worker_metrics("reconcile_star_transactions", "maintain", "skipped", started)
        return 0
    try:
        count = await run_star_reconciliation(
            ctx["session_factory"],  # type: ignore[arg-type]
            AiogramStarsGateway(bot),
            settings,
        )
        outcome = "succeeded" if count else "empty"
        return count
    finally:
        _record_worker_metrics("reconcile_star_transactions", "maintain", outcome, started)


async def process_referral_rewards(ctx: dict[str, object]) -> int:
    started = monotonic()
    outcome = "failed"
    settings = cast(Settings, ctx.get("settings") or get_settings())
    try:
        count = await process_due_referral_rewards(
            ctx["session_factory"],  # type: ignore[arg-type]
            settings,
        )
        outcome = "succeeded" if count else "empty"
        return count
    finally:
        _record_worker_metrics("process_referral_rewards", "maintain", outcome, started)


async def expire_due_subscriptions(ctx: dict[str, object]) -> int:
    """Retire subscriptions whose paid period has ended.

    The counterweight to billing: Telegram stops charging, but only this takes the tier
    away, so without it a lapsed or cancelled subscriber would keep their plan for ever.
    It grants nothing and calls no Telegram API, so it needs no bot token and is safe to
    run wherever the database is reachable.
    """
    started = monotonic()
    outcome = "failed"
    settings = cast(Settings, ctx.get("settings") or get_settings())
    if not settings.subscriptions_enabled:
        _record_worker_metrics("expire_due_subscriptions", "maintain", "skipped", started)
        return 0
    try:
        count = await process_due_subscriptions(
            ctx["session_factory"],  # type: ignore[arg-type]
            settings,
        )
        outcome = "succeeded" if count else "empty"
        return count
    finally:
        _record_worker_metrics("expire_due_subscriptions", "maintain", outcome, started)


def _record_worker_metrics(job: str, queue: str, outcome: str, started: float) -> None:
    tags = {"queue": queue, "job": job, "outcome": outcome}
    metrics = get_metrics()
    metrics.incr("worker.job", tags=tags)
    metrics.observe("worker.job_duration_seconds", monotonic() - started, tags=tags)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class ImageWorkerSettings:
    """Run with: arq apps.worker.main.ImageWorkerSettings"""

    functions = [process_generation]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:image"
    max_jobs = 4
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings()


class TextWorkerSettings:
    """Run with: arq apps.worker.main.TextWorkerSettings"""

    functions = [process_generation]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:text"
    max_jobs = 8
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings()


class VideoWorkerSettings:
    """Run with: arq apps.worker.main.VideoWorkerSettings — low concurrency."""

    functions = [process_generation]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:video"
    max_jobs = 2
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings()


class MaintainWorkerSettings:
    """Poll due jobs + sweep stuck generations for recovery after worker death."""

    functions = [
        poll_due_generations,
        sweep_stuck_generations,
        sweep_expired_reservations,
        dispatch_generation_notifications,
        process_star_refund,
        reconcile_star_payments,
        process_referral_rewards,
        expire_due_subscriptions,
    ]
    cron_jobs = [
        cron(poll_due_generations, second=set(range(0, 60, 5))),
        cron(sweep_stuck_generations, second={15, 45}),
        # Hourly is deliberate. This is the backstop for holds the generation
        # paths failed to finalise at all, and every candidate it finds is
        # already hours past its deadline, so a tight schedule would only add
        # empty queries. Frequent enough that a stranded balance is corrected
        # the same session it happened.
        cron(sweep_expired_reservations, minute={7}),
        cron(
            dispatch_generation_notifications,
            second={5, 15, 25, 35, 45, 55},
        ),
        cron(process_star_refund, second={8, 18, 28, 38, 48, 58}),
        cron(
            reconcile_star_payments,
            minute={0, 10, 20, 30, 40, 50},
            second={30},
        ),
        cron(process_referral_rewards, minute=set(range(60)), second={40}),
        # Every five minutes is ample: the deadline is a date Telegram set 30 days earlier,
        # so a few minutes of overshoot is invisible and a tighter schedule only adds
        # empty queries.
        cron(expire_due_subscriptions, minute=set(range(0, 60, 5)), second={20}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "kelbet:maintain"
    max_jobs = 1
    job_timeout = get_settings().worker_job_timeout_seconds
    redis_settings = _redis_settings()


# Back-compat alias
WorkerSettings = ImageWorkerSettings


async def _idle_stub() -> None:
    settings = get_settings()
    initialize_observability(settings, component="worker")
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
        initialize_observability(settings, component="worker")
        logger.error(
            "Start ARQ with ImageWorkerSettings, TextWorkerSettings, "
            "VideoWorkerSettings, and MaintainWorkerSettings"
        )
        asyncio.run(_idle_stub())
        return
    asyncio.run(_idle_stub())


if __name__ == "__main__":
    main()
