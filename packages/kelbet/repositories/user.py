from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import User
from kelbet.domain.enums import Language, Plan


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        telegram_id: int,
        username: str | None,
        language: Language,
        plan: Plan = Plan.FREE,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            language=language.value,
            plan=plan.value,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def update_language(self, user: User, language: Language) -> User:
        user.language = language.value
        await self._session.flush()
        return user

    async def update_username(self, user: User, username: str | None) -> User:
        user.username = username
        await self._session.flush()
        return user

    async def update_generation_notifications(
        self,
        user: User,
        enabled: bool,
    ) -> User:
        user.notify_generation_ready = enabled
        await self._session.flush()
        return user
