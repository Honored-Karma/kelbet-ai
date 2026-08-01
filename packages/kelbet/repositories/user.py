from contextlib import suppress
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import User
from kelbet.domain.enums import Language, Plan
from kelbet.domain.exceptions import UserBlockedError


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_id_for_update(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, user_id: UUID) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def search(self, query: str, *, limit: int = 20) -> list[User]:
        value = query.strip().lstrip("@").lower()
        filters = []
        if value.isascii() and value.isdigit():
            filters.append(User.telegram_id == int(value))
        with suppress(ValueError):
            filters.append(User.id == UUID(value))
        if value:
            escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            filters.append(User.username.ilike(f"{escaped}%", escape="\\"))
        if not filters:
            return []
        result = await self._session.execute(
            select(User).where(or_(*filters)).order_by(User.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def assert_paid_operations_allowed(self, user_id: UUID) -> User:
        user = await self.get_by_id_for_update(user_id)
        if user is None:
            from kelbet.domain.exceptions import UserNotFoundError

            raise UserNotFoundError(f"User {user_id} not found")
        if user.is_blocked:
            raise UserBlockedError(f"User {user_id} is blocked")
        return user

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
