import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.domain.enums import Language
from kelbet.ops.grant_credits import GrantCreditsError, grant_credits
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository


@pytest.mark.asyncio
async def test_operator_grant_is_ledger_backed_and_idempotent(session: AsyncSession) -> None:
    users = UserRepository(session)
    wallets = WalletRepository(session)
    user = await users.create(
        telegram_id=8_201_681_157,
        username="owner",
        language=Language.RU,
    )
    wallet = await wallets.create(user.id)

    first = await grant_credits(
        session,
        telegram_id=user.telegram_id,
        amount=1_000,
        reference="owner-test-20260731",
    )
    replay = await grant_credits(
        session,
        telegram_id=user.telegram_id,
        amount=1_000,
        reference="owner-test-20260731",
    )

    assert first.applied is True
    assert first.balance_before == 0
    assert first.balance_after == 1_000
    assert replay.applied is False
    assert replay.balance_after == 1_000
    assert await wallets.count_transactions(wallet.id) == 1


@pytest.mark.asyncio
async def test_operator_grant_requires_existing_user(session: AsyncSession) -> None:
    with pytest.raises(GrantCreditsError, match="run /start first"):
        await grant_credits(
            session,
            telegram_id=9_999_999,
            amount=100,
            reference="missing-user",
        )


@pytest.mark.asyncio
async def test_operator_grant_rejects_unsafe_amount(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="between 1"):
        await grant_credits(
            session,
            telegram_id=1,
            amount=1_000_001,
            reference="too-much",
        )
