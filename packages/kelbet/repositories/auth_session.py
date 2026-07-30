from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import AuthSession


class AuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        telegram_auth_date: datetime,
        init_data_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> AuthSession:
        row = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            telegram_auth_date=telegram_auth_date,
            init_data_hash=init_data_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        result = await self._session.execute(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_row: AuthSession, *, revoked_at: datetime) -> AuthSession:
        session_row.revoked_at = revoked_at
        await self._session.flush()
        return session_row
