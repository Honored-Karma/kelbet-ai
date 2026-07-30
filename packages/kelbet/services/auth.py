from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.auth import (
    ReplayStore,
    assert_not_replayed,
    hash_token,
    resolve_language,
    validate_init_data,
)
from kelbet.config import Settings, get_settings
from kelbet.domain.enums import Language
from kelbet.domain.exceptions import InvalidSessionError
from kelbet.repositories.auth_session import AuthSessionRepository
from kelbet.repositories.user import UserRepository
from kelbet.services.registration import RegistrationService


@dataclass(frozen=True, slots=True)
class AuthTokenResult:
    access_token: str
    token_type: str
    expires_in: int
    user_id: UUID
    telegram_id: int
    language: Language
    plan: str
    welcome_applied: bool


@dataclass(frozen=True, slots=True)
class SessionUser:
    session_id: UUID
    user_id: UUID
    telegram_id: int
    username: str | None
    language: Language
    plan: str


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        replay_store: ReplayStore,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._replay = replay_store
        self._settings = settings or get_settings()
        self._auth_sessions = AuthSessionRepository(session)
        self._users = UserRepository(session)
        self._registration = RegistrationService(session, self._settings)

    async def login_with_init_data(
        self,
        init_data: str,
        *,
        user_agent: str | None = None,
        ip_hash: str | None = None,
        now: datetime | None = None,
    ) -> AuthTokenResult:
        current = now or datetime.now(UTC)
        validated = validate_init_data(
            init_data,
            self._settings.bot_token,
            max_age_seconds=self._settings.telegram_auth_max_age_seconds,
            now=current,
        )
        await assert_not_replayed(
            self._replay,
            init_data_hash=validated.init_data_hash,
            ttl_seconds=self._settings.telegram_auth_max_age_seconds,
        )

        language = resolve_language(validated.user.language_code)
        user_dto, credit = await self._registration.register_with_language(
            telegram_id=validated.user.id,
            username=validated.user.username,
            language=language,
        )

        raw_token = secrets.token_urlsafe(32)
        expires_at = current + timedelta(seconds=self._settings.session_ttl_seconds)
        await self._auth_sessions.create(
            user_id=user_dto.id,
            token_hash=hash_token(raw_token),
            telegram_auth_date=validated.auth_date,
            init_data_hash=validated.init_data_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )

        return AuthTokenResult(
            access_token=raw_token,
            token_type="bearer",
            expires_in=self._settings.session_ttl_seconds,
            user_id=user_dto.id,
            telegram_id=user_dto.telegram_id,
            language=user_dto.language,
            plan=user_dto.plan.value,
            welcome_applied=credit.applied,
        )

    async def resolve_session(
        self,
        access_token: str,
        *,
        now: datetime | None = None,
    ) -> SessionUser:
        if not access_token:
            raise InvalidSessionError("missing access token")

        current = now or datetime.now(UTC)
        row = await self._auth_sessions.get_by_token_hash(hash_token(access_token))
        if row is None or row.revoked_at is not None:
            raise InvalidSessionError("invalid session")
        if row.expires_at <= current:
            raise InvalidSessionError("session expired")

        user = await self._users.get_by_id(row.user_id)
        if user is None:
            raise InvalidSessionError("user missing")

        return SessionUser(
            session_id=row.id,
            user_id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            language=Language(user.language),
            plan=user.plan,
        )

    async def logout(
        self,
        access_token: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        row = await self._auth_sessions.get_by_token_hash(hash_token(access_token))
        if row is None:
            return False
        if row.revoked_at is not None:
            return False
        await self._auth_sessions.revoke(row, revoked_at=current)
        return True
