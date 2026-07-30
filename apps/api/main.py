from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiogram import Bot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from apps.api.errors import register_exception_handlers
from apps.api.middleware import CorrelationIdMiddleware
from apps.api.routes.health import router as health_router
from apps.api.routes.v1 import api_v1_router
from kelbet.auth import MemoryReplayStore, RedisReplayStore
from kelbet.chat.factory import build_chat_provider
from kelbet.chat.mock import MockChatProvider
from kelbet.config import cors_origin_list, get_settings
from kelbet.db.session import build_session_factory
from kelbet.observability import configure_json_logging
from kelbet.payments.gateway import AiogramStarsGateway, DisabledPaymentGateway, MockPaymentGateway
from kelbet.queue import ArqGenerationQueue, InlineGenerationQueue
from kelbet.rate_limit import MemoryRateLimiter, RedisRateLimiter
from kelbet.storage import MemoryObjectStorage, build_object_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_json_logging(settings.log_level)
    if not getattr(app.state, "session_factory", None):
        app.state.session_factory = build_session_factory(settings)
    if getattr(app.state, "object_storage", None) is None:
        app.state.object_storage = build_object_storage(settings)
    if getattr(app.state, "chat_provider", None) is None:
        app.state.chat_provider = build_chat_provider(settings)

    redis: Redis[Any] | None = None
    arq_pool: Any | None = None
    payment_bot: Bot | None = None
    if getattr(app.state, "replay_store", None) is None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        app.state.redis = redis
        app.state.replay_store = RedisReplayStore(redis)
        app.state.rate_limiter = RedisRateLimiter(redis)

    if getattr(app.state, "rate_limiter", None) is None:
        app.state.rate_limiter = MemoryRateLimiter()

    if getattr(app.state, "generation_queue", None) is None:
        if settings.generation_queue_backend.strip().lower() == "arq":
            from arq import create_pool
            from arq.connections import RedisSettings

            arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            app.state.arq_pool = arq_pool
            app.state.generation_queue = ArqGenerationQueue(arq_pool)
        else:
            app.state.generation_queue = InlineGenerationQueue()

    if getattr(app.state, "payment_gateway", None) is None:
        if settings.payments_enabled and settings.bot_token:
            payment_bot = Bot(token=settings.bot_token)
            app.state.payment_gateway = AiogramStarsGateway(payment_bot)
        else:
            app.state.payment_gateway = DisabledPaymentGateway()

    try:
        yield
    finally:
        if arq_pool is not None:
            await arq_pool.close()
        if redis is not None:
            await redis.close()
        if payment_bot is not None:
            await payment_bot.session.close()


def create_app(*, testing: bool = False) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="KELBET AI API",
        version="0.3.0",
        lifespan=None if testing else lifespan,
    )
    if testing:
        configure_json_logging(settings.log_level)
        app.state.replay_store = MemoryReplayStore()
        app.state.redis = None
        app.state.rate_limiter = MemoryRateLimiter()
        app.state.object_storage = MemoryObjectStorage(
            bucket_name=settings.s3_bucket or "kelbet-assets"
        )
        app.state.chat_provider = MockChatProvider(
            model=settings.openrouter_model or "mock-model"
        )
        app.state.generation_queue = InlineGenerationQueue()
        app.state.payment_gateway = MockPaymentGateway()

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origin_list(settings),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app
