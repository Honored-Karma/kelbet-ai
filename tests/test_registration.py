import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.registration import RegistrationService, welcome_idempotency_key


@pytest.mark.asyncio
async def test_registration_grants_welcome_credits_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        start = await service.handle_start(telegram_id=2001, username="alice")
        assert start.needs_language is True

        user, credit = await service.register_with_language(
            telegram_id=2001,
            username="alice",
            language=Language.RU,
        )
        assert credit.applied is True
        assert user.balance == 5
        assert user.language == Language.RU
        assert user.plan.value == "free"
        user_id = user.id

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        start = await service.handle_start(telegram_id=2001, username="alice")
        assert start.needs_language is False
        assert start.user is not None
        assert start.user.balance == 5

        user2, credit2 = await service.register_with_language(
            telegram_id=2001,
            username="alice",
            language=Language.KK,
        )
        assert credit2.applied is False
        assert user2.balance == 5
        assert user2.language == Language.KK

        wallets = WalletRepository(session)
        wallet = await wallets.get_by_user_id(user_id)
        assert wallet is not None
        assert await wallets.count_transactions(wallet.id) == 1
        existing = await wallets.get_transaction_by_idempotency_key(
            welcome_idempotency_key(user_id)
        )
        assert existing is not None
        assert existing.amount == 5


@pytest.mark.asyncio
async def test_login_does_not_overwrite_chosen_language(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        await service.register_with_language(
            telegram_id=2003,
            username="dana",
            language=Language.KK,
        )

    # Мини-апп логинится с языком из Telegram initData (например, ru),
    # но выбранный пользователем язык не должен перезаписываться.
    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        user, credit = await service.register_with_language(
            telegram_id=2003,
            username="dana",
            language=Language.RU,
            overwrite_language=False,
        )
        assert credit.applied is False
        assert user.language == Language.KK


@pytest.mark.asyncio
async def test_repeated_start_does_not_create_duplicate_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        await service.register_with_language(
            telegram_id=2002,
            username="bob",
            language=Language.KK,
        )

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        first = await service.handle_start(2002, "bob")
        second = await service.handle_start(2002, "bob_new")
        assert first.needs_language is False
        assert second.needs_language is False
        assert first.user is not None
        assert second.user is not None
        assert first.user.id == second.user.id
        assert second.user.username == "bob_new"
        assert second.user.balance == 5
