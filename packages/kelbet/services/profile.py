from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
    plan: Plan


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)

    async def get_profile(self, telegram_id: int) -> ProfileDTO:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError(f"User telegram_id={telegram_id} not found")

        wallet = await self._wallets.get_by_user_id(user.id)
        balance = wallet.balance if wallet is not None else 0

        return ProfileDTO(
            user_id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            language=Language(user.language),
            balance=balance,
            plan=Plan(user.plan),
        )
