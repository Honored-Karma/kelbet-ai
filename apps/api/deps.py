"""FastAPI dependencies for session, auth, and settings."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.auth import MemoryReplayStore, ReplayStore
from kelbet.chat import ChatProvider
from kelbet.chat.factory import build_chat_provider
from kelbet.config import Settings, admin_bootstrap_id_set, get_settings
from kelbet.domain.enums import OperatorRole
from kelbet.domain.exceptions import (
    AdminAuthorizationError,
    InvalidSessionError,
    ModerationRateLimitError,
    ModerationRejectedError,
    RateLimitExceededError,
)
from kelbet.payments.gateway import DisabledPaymentGateway, PaymentInvoiceGateway
from kelbet.queue import GenerationQueue, InlineGenerationQueue
from kelbet.rate_limit import MemoryRateLimiter, RateLimiter
from kelbet.repositories.admin import AdminRepository
from kelbet.services.admin import OperatorContext
from kelbet.services.auth import AuthService, SessionUser
from kelbet.storage import MemoryObjectStorage, ObjectStorage

_bearer = HTTPBearer(auto_error=False)


async def get_settings_dep() -> Settings:
    return get_settings()


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except (ModerationRejectedError, ModerationRateLimitError):
            await session.commit()
            raise
        except Exception:
            await session.rollback()
            raise


def get_replay_store(request: Request) -> ReplayStore:
    store = getattr(request.app.state, "replay_store", None)
    if store is None:
        store = MemoryReplayStore()
        request.app.state.replay_store = store
    return store


def get_object_storage(request: Request) -> ObjectStorage:
    storage = getattr(request.app.state, "object_storage", None)
    if storage is None:
        storage = MemoryObjectStorage()
        request.app.state.object_storage = storage
    return storage


def get_generation_queue(request: Request) -> GenerationQueue:
    queue = getattr(request.app.state, "generation_queue", None)
    if queue is None:
        queue = InlineGenerationQueue()
        request.app.state.generation_queue = queue
    return queue


def get_chat_provider(request: Request) -> ChatProvider:
    provider = getattr(request.app.state, "chat_provider", None)
    if provider is None:
        provider = build_chat_provider(get_settings())
        request.app.state.chat_provider = provider
    return provider


def get_payment_gateway(request: Request) -> PaymentInvoiceGateway:
    gateway = getattr(request.app.state, "payment_gateway", None)
    if gateway is None:
        gateway = DisabledPaymentGateway()
        request.app.state.payment_gateway = gateway
    return gateway


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        limiter = MemoryRateLimiter()
        request.app.state.rate_limiter = limiter
    return limiter


async def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    replay_store: ReplayStore = Depends(get_replay_store),
    settings: Settings = Depends(get_settings_dep),
) -> AuthService:
    return AuthService(session, replay_store, settings)


async def get_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise InvalidSessionError("missing bearer token")
    return credentials.credentials


async def get_current_user(
    access_token: str = Depends(get_access_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> SessionUser:
    return await auth_service.resolve_session(access_token)


async def get_operator(
    request: Request,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> OperatorContext:
    if not settings.admin_enabled:
        raise AdminAuthorizationError("Operator surface is disabled")

    bootstrap = current.telegram_id in admin_bootstrap_id_set(settings)
    if bootstrap:
        role = OperatorRole.ADMIN
    else:
        membership = await AdminRepository(session).get_membership(current.user_id)
        if membership is None:
            raise AdminAuthorizationError("Operator role required")
        try:
            role = OperatorRole(membership.role)
        except ValueError as exc:
            raise AdminAuthorizationError("Invalid operator role") from exc

    allowed = await limiter.hit(
        f"admin:{current.user_id}:{request.url.path}",
        limit=settings.admin_rate_limit_per_minute,
        window_seconds=60,
    )
    if not allowed:
        raise RateLimitExceededError("Admin rate limit exceeded")
    return OperatorContext(
        user_id=current.user_id,
        telegram_id=current.telegram_id,
        username=current.username,
        role=role,
        bootstrap=bootstrap,
    )


async def require_admin(
    operator: OperatorContext = Depends(get_operator),
) -> OperatorContext:
    if not operator.can_write:
        raise AdminAuthorizationError("Admin role required")
    return operator


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def rate_limit_auth(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    if not settings.rate_limit_enabled:
        return
    allowed = await limiter.hit(
        f"auth:{_client_ip(request)}",
        limit=settings.rate_limit_auth_per_minute,
        window_seconds=60,
    )
    if not allowed:
        raise RateLimitExceededError("Auth rate limit exceeded")


async def rate_limit_generations(
    request: Request,
    current: SessionUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    if not settings.rate_limit_enabled:
        return
    allowed = await limiter.hit(
        f"gen:{current.user_id}",
        limit=settings.rate_limit_generations_per_minute,
        window_seconds=60,
    )
    if not allowed:
        raise RateLimitExceededError("Generation rate limit exceeded")


async def rate_limit_prompt_assistant(
    request: Request,
    current: SessionUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    if not settings.rate_limit_enabled:
        return
    allowed = await limiter.hit(
        f"prompt-assistant:{current.user_id}",
        limit=settings.rate_limit_prompt_assistant_per_minute,
        window_seconds=60,
    )
    if not allowed:
        raise RateLimitExceededError("Prompt assistant rate limit exceeded")
