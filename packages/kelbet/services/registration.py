from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models import User, Wallet
from kelbet.domain.enums import Language, Plan, TxReason
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.wallet import CreditResult, WalletService


@dataclass(frozen=True, slots=True)
class UserDTO:
    id: UUID
    telegram_id: int
    username: str | None
    language: Language
    plan: Plan
    balance: int


@dataclass(frozen=True, slots=True)
class StartResult:
    needs_language: bool
    user: UserDTO | None
    welcome_applied: bool = False


def welcome_idempotency_key(user_id: UUID) -> str:
    return f"welcome:{user_id}"


class RegistrationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)
        self._wallet_service = WalletService(session)

    async def handle_start(self, telegram_id: int, username: str | None) -> StartResult:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            return StartResult(needs_language=True, user=None)

        if username != user.username:
            await self._users.update_username(user, username)

        dto = await self._to_dto(user)
        return StartResult(needs_language=False, user=dto)

    async def register_with_language(
        self,
        *,
        telegram_id: int,
        username: str | None,
        language: Language,
        overwrite_language: bool = True,
        referral_code: str | None = None,
    ) -> tuple[UserDTO, CreditResult]:
        user, created = await self._get_or_create_user(
            telegram_id=telegram_id,
            username=username,
            language=language,
            overwrite_language=overwrite_language,
        )
        wallet = await self._get_or_create_wallet(user.id)

        if created and referral_code:
            from kelbet.services.referral import ReferralService

            await ReferralService(self._session, self._settings).attribute_new_user(
                invited_user_id=user.id,
                code=referral_code,
                created_in_registration=True,
            )

        credit_result = await self._wallet_service.credit(
            wallet.id,
            self._settings.welcome_credits,
            TxReason.WELCOME_BONUS,
            welcome_idempotency_key(user.id),
            meta={"source": "registration"},
        )

        dto = UserDTO(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            language=Language(user.language),
            plan=Plan(user.plan),
            balance=credit_result.balance,
        )
        return dto, credit_result

    async def _get_or_create_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        language: Language,
        overwrite_language: bool = True,
    ) -> tuple[User, bool]:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is not None:
            return (
                await self._sync_existing_user(user, username, language, overwrite_language),
                False,
            )

        try:
            async with self._session.begin_nested():
                user = await self._users.create(
                    telegram_id=telegram_id,
                    username=username,
                    language=language,
                    plan=Plan.FREE,
                )
                return user, True
        except IntegrityError:
            user = await self._users.get_by_telegram_id(telegram_id)
            if user is None:
                raise
            return (
                await self._sync_existing_user(user, username, language, overwrite_language),
                False,
            )

    async def _sync_existing_user(
        self,
        user: User,
        username: str | None,
        language: Language,
        overwrite_language: bool,
    ) -> User:
        if overwrite_language and user.language != language.value:
            await self._users.update_language(user, language)
        if username != user.username:
            await self._users.update_username(user, username)
        return user

    async def _get_or_create_wallet(self, user_id: UUID) -> Wallet:
        wallet = await self._wallets.get_by_user_id(user_id)
        if wallet is not None:
            return wallet

        try:
            async with self._session.begin_nested():
                return await self._wallets.create(user_id)
        except IntegrityError:
            wallet = await self._wallets.get_by_user_id(user_id)
            if wallet is None:
                raise
            return wallet

    async def _to_dto(self, user: User) -> UserDTO:
        wallet = await self._wallets.get_by_user_id(user.id)
        balance = wallet.balance if wallet is not None else 0
        return UserDTO(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            language=Language(user.language),
            plan=Plan(user.plan),
            balance=balance,
        )
