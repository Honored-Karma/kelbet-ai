"""Registration and repeated /start idempotency tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.registration import RegistrationService, welcome_idempotency_key


@pytest.mark.asyncio
async def test_repeated_start_does_not_grant_credits_again(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        user, credit = await service.register_with_language(
            telegram_id=3001,
            username="carol",
            language=Language.RU,
        )
        assert credit.applied is True
        assert user.balance == 5
        user_id = user.id

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        again = await service.handle_start(3001, "carol")
        assert again.needs_language is False
        assert again.user is not None
        assert again.user.balance == 5

        _, credit2 = await service.register_with_language(
            telegram_id=3001,
            username="carol",
            language=Language.RU,
        )
        assert credit2.applied is False
        assert credit2.balance == 5

        wallets = WalletRepository(session)
        wallet = await wallets.get_by_user_id(user_id)
        assert wallet is not None
        assert wallet.balance == 5
        assert await wallets.count_transactions(wallet.id) == 1
        tx = await wallets.get_transaction_by_idempotency_key(welcome_idempotency_key(user_id))
        assert tx is not None
        assert tx.reason == "welcome_bonus"
