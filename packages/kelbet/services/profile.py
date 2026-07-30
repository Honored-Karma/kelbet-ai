from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import User
from kelbet.domain.enums import Language, Plan
from kelbet.domain.exceptions import UserNotFoundError
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository


@dataclass(frozen=True, slots=True)
class ProfileDTO:
    user_id: UUID
    telegram_id: int
    username: str | None
    language: Language
    balance: int
    reserved: int
    available: int
    plan: Plan
    notify_generation_ready: bool


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)

    async def get_profile(self, telegram_id: int) -> ProfileDTO:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError(f"User telegram_id={telegram_id} not found")
        return await self._from_user(user)

    async def get_profile_by_user_id(self, user_id: UUID) -> ProfileDTO:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User id={user_id} not found")
        return await self._from_user(user)

    async def update_language(self, user_id: UUID, language: Language) -> ProfileDTO:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User id={user_id} not found")
        await self._users.update_language(user, language)
        return await self._from_user(user)

    async def update_generation_notifications(
        self,
        user_id: UUID,
        enabled: bool,
    ) -> ProfileDTO:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User id={user_id} not found")
        await self._users.update_generation_notifications(user, enabled)
        return await self._from_user(user)

    async def _from_user(self, user: User) -> ProfileDTO:
        wallet = await self._wallets.get_by_user_id(user.id)
        balance = wallet.balance if wallet is not None else 0
        reserved = wallet.reserved if wallet is not None else 0
        return ProfileDTO(
            user_id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            language=Language(user.language),
            balance=balance,
            reserved=reserved,
            available=balance - reserved,
            plan=Plan(user.plan),
            notify_generation_ready=user.notify_generation_ready,
        )
