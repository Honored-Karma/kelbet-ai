"""Concurrent registration and welcome-bonus race tests."""

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import CreditTransaction, User
from kelbet.domain.enums import Language
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.registration import RegistrationService, welcome_idempotency_key


@pytest.mark.asyncio
async def test_concurrent_registration_grants_welcome_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)
    telegram_id = 4001

    async def register(language: Language) -> tuple[bool, int]:
        async with session_factory() as session, session.begin():
            service = RegistrationService(session, settings=settings)
            user, credit = await service.register_with_language(
                telegram_id=telegram_id,
                username="race",
                language=language,
            )
            return credit.applied, user.balance

    first, second = await asyncio.gather(
        register(Language.RU),
        register(Language.KK),
    )

    applied_flags = {first[0], second[0]}
    assert True in applied_flags
    assert False in applied_flags
    assert first[1] == 5
    assert second[1] == 5

    async with session_factory() as session, session.begin():
        users_count = await session.scalar(
            select(func.count()).select_from(User).where(User.telegram_id == telegram_id)
        )
        assert users_count == 1

        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None

        wallets = WalletRepository(session)
        wallet = await wallets.get_by_user_id(user.id)
        assert wallet is not None
        assert wallet.balance == 5
        assert await wallets.count_transactions(wallet.id) == 1

        tx = await wallets.get_transaction_by_idempotency_key(welcome_idempotency_key(user.id))
        assert tx is not None
        assert tx.reason == "welcome_bonus"
        assert tx.amount == 5

        welcome_rows = await session.scalar(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.idempotency_key == welcome_idempotency_key(user.id))
        )
        assert welcome_rows == 1


@pytest.mark.asyncio
async def test_welcome_bonus_cannot_be_applied_twice_under_concurrency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)
    telegram_id = 4002

    async with session_factory() as session, session.begin():
        service = RegistrationService(session, settings=settings)
        user, credit = await service.register_with_language(
            telegram_id=telegram_id,
            username="once",
            language=Language.RU,
        )
        assert credit.applied is True
        user_id = user.id

    async def re_register() -> bool:
        async with session_factory() as session, session.begin():
            service = RegistrationService(session, settings=settings)
            _, credit_result = await service.register_with_language(
                telegram_id=telegram_id,
                username="once",
                language=Language.KK,
            )
            return credit_result.applied

    results = await asyncio.gather(re_register(), re_register(), re_register())
    assert all(applied is False for applied in results)

    async with session_factory() as session, session.begin():
        wallets = WalletRepository(session)
        wallet = await wallets.get_by_user_id(user_id)
        assert wallet is not None
        assert wallet.balance == 5
        assert await wallets.count_transactions(wallet.id) == 1
