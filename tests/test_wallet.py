from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.db.models import User, Wallet
from kelbet.domain.enums import Language, Plan, ReservationStatus, TxReason
from kelbet.domain.exceptions import (
    InsufficientCreditsError,
    InvalidReservationStateError,
)
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.wallet import WalletService


async def _seed_wallet(
    session: AsyncSession, *, telegram_id: int, credits: int
) -> tuple[User, Wallet, WalletService, WalletRepository]:
    users = UserRepository(session)
    wallets = WalletRepository(session)
    service = WalletService(session)
    user = await users.create(
        telegram_id=telegram_id,
        username="tester",
        language=Language.RU,
        plan=Plan.FREE,
    )
    wallet = await wallets.create(user.id)
    if credits:
        await service.credit(
            wallet.id,
            credits,
            TxReason.WELCOME_BONUS,
            f"welcome:{user.id}",
        )
    return user, wallet, service, wallets


@pytest.mark.asyncio
async def test_credit_is_idempotent(session: AsyncSession) -> None:
    users = UserRepository(session)
    wallets = WalletRepository(session)
    service = WalletService(session)

    user = await users.create(
        telegram_id=1001,
        username="tester",
        language=Language.RU,
        plan=Plan.FREE,
    )
    wallet = await wallets.create(user.id)
    key = f"welcome:{user.id}"

    first = await service.credit(wallet.id, 5, TxReason.WELCOME_BONUS, key)
    second = await service.credit(wallet.id, 5, TxReason.WELCOME_BONUS, key)

    assert first.applied is True
    assert first.balance == 5
    assert second.applied is False
    assert second.balance == 5
    assert await wallets.count_transactions(wallet.id) == 1

    refreshed = await wallets.get_by_id(wallet.id)
    assert refreshed is not None
    assert refreshed.balance == 5
    assert refreshed.reserved == 0


@pytest.mark.asyncio
async def test_credit_different_keys_stack(session: AsyncSession) -> None:
    users = UserRepository(session)
    wallets = WalletRepository(session)
    service = WalletService(session)

    user = await users.create(
        telegram_id=1002,
        username=None,
        language=Language.KK,
    )
    wallet = await wallets.create(user.id)

    await service.credit(wallet.id, 5, TxReason.WELCOME_BONUS, f"welcome:{user.id}")
    await service.credit(wallet.id, 3, "promo", f"promo:{uuid4()}")

    refreshed = await wallets.get_by_id(wallet.id)
    assert refreshed is not None
    assert refreshed.balance == 8
    assert await wallets.count_transactions(wallet.id) == 2


@pytest.mark.asyncio
async def test_reserve_capture_happy_path(session: AsyncSession) -> None:
    user, wallet, service, wallets = await _seed_wallet(session, telegram_id=2001, credits=10)

    reserved = await service.reserve(
        wallet.id,
        4,
        f"reserve:{uuid4()}",
        user_id=user.id,
        quote_snapshot={"model_slug": "mock-image", "user_credit_price": 4},
    )
    assert reserved.applied is True
    assert reserved.status is ReservationStatus.HELD
    assert reserved.balance == 10
    assert reserved.reserved == 4
    assert reserved.available == 6

    captured = await service.capture(reserved.reservation_id)
    assert captured.applied is True
    assert captured.status is ReservationStatus.CAPTURED
    assert captured.balance == 6
    assert captured.reserved == 0
    assert captured.available == 6
    assert await wallets.count_transactions(wallet.id) == 2  # welcome + capture

    again = await service.capture(reserved.reservation_id)
    assert again.applied is False
    assert again.status is ReservationStatus.CAPTURED
    assert await wallets.count_transactions(wallet.id) == 2


@pytest.mark.asyncio
async def test_reserve_release_happy_path(session: AsyncSession) -> None:
    user, wallet, service, wallets = await _seed_wallet(session, telegram_id=2002, credits=10)

    reserved = await service.reserve(
        wallet.id,
        3,
        f"reserve:{uuid4()}",
        user_id=user.id,
    )
    released = await service.release(reserved.reservation_id)
    assert released.applied is True
    assert released.status is ReservationStatus.RELEASED
    assert released.balance == 10
    assert released.reserved == 0
    assert await wallets.count_transactions(wallet.id) == 1  # no ledger on release

    again = await service.release(reserved.reservation_id)
    assert again.applied is False
    assert again.reserved == 0


@pytest.mark.asyncio
async def test_reserve_is_idempotent(session: AsyncSession) -> None:
    user, wallet, service, _wallets = await _seed_wallet(session, telegram_id=2003, credits=5)
    key = f"reserve:idem:{user.id}"

    first = await service.reserve(wallet.id, 2, key, user_id=user.id)
    second = await service.reserve(wallet.id, 2, key, user_id=user.id)

    assert first.applied is True
    assert second.applied is False
    assert second.reservation_id == first.reservation_id
    assert second.reserved == 2


@pytest.mark.asyncio
async def test_reserve_insufficient_available(session: AsyncSession) -> None:
    user, wallet, service, _wallets = await _seed_wallet(session, telegram_id=2004, credits=5)
    await service.reserve(wallet.id, 4, f"reserve:{uuid4()}", user_id=user.id)

    with pytest.raises(InsufficientCreditsError):
        await service.reserve(wallet.id, 2, f"reserve:{uuid4()}", user_id=user.id)


@pytest.mark.asyncio
async def test_debit_respects_reserved(session: AsyncSession) -> None:
    user, wallet, service, _wallets = await _seed_wallet(session, telegram_id=2005, credits=5)
    await service.reserve(wallet.id, 4, f"reserve:{uuid4()}", user_id=user.id)

    with pytest.raises(InsufficientCreditsError):
        await service.debit(wallet.id, 2, TxReason.AI_CHAT, f"chat:{uuid4()}")

    ok = await service.debit(wallet.id, 1, TxReason.AI_CHAT, f"chat:{uuid4()}")
    assert ok.applied is True
    assert ok.balance == 4


@pytest.mark.asyncio
async def test_cannot_release_captured(session: AsyncSession) -> None:
    user, wallet, service, _wallets = await _seed_wallet(session, telegram_id=2006, credits=5)
    reserved = await service.reserve(wallet.id, 2, f"reserve:{uuid4()}", user_id=user.id)
    await service.capture(reserved.reservation_id)

    with pytest.raises(InvalidReservationStateError):
        await service.release(reserved.reservation_id)


@pytest.mark.asyncio
async def test_refund_after_capture(session: AsyncSession) -> None:
    user, wallet, service, wallets = await _seed_wallet(session, telegram_id=2007, credits=5)
    reserved = await service.reserve(wallet.id, 3, f"reserve:{uuid4()}", user_id=user.id)
    await service.capture(reserved.reservation_id)

    refunded = await service.refund(reserved.reservation_id)
    assert refunded.applied is True
    assert refunded.balance == 5
    assert refunded.reserved == 0
    assert await wallets.count_transactions(wallet.id) == 3  # welcome + capture + refund

    again = await service.refund(reserved.reservation_id)
    assert again.applied is False
    assert await wallets.count_transactions(wallet.id) == 3


@pytest.mark.asyncio
async def test_concurrent_reserves_do_not_oversell(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as setup, setup.begin():
        user, wallet, service, _wallets = await _seed_wallet(setup, telegram_id=3001, credits=5)
        user_id = user.id
        wallet_id = wallet.id

    async def try_reserve(key_suffix: int) -> bool:
        async with session_factory() as db, db.begin():
            svc = WalletService(db)
            try:
                result = await svc.reserve(
                    wallet_id,
                    3,
                    f"reserve:concurrent:{key_suffix}",
                    user_id=user_id,
                )
                return result.applied
            except InsufficientCreditsError:
                return False

    import asyncio

    outcomes = await asyncio.gather(*(try_reserve(i) for i in range(8)))
    assert sum(outcomes) == 1

    async with session_factory() as db, db.begin():
        wallets = WalletRepository(db)
        refreshed = await wallets.get_by_id(wallet_id)
        assert refreshed is not None
        assert refreshed.balance == 5
        assert refreshed.reserved == 3
        assert refreshed.available == 2
