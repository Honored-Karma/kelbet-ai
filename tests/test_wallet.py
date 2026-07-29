from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.domain.enums import Language, Plan, TxReason
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.wallet import WalletService


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
