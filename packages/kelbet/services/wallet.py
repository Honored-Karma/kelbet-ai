from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import CreditTransaction, Wallet
from kelbet.domain.enums import TxReason, TxType
from kelbet.domain.exceptions import (
    InsufficientCreditsError,
    WalletNotFoundError,
)
from kelbet.repositories.wallet import WalletRepository


@dataclass(frozen=True, slots=True)
class CreditResult:
    applied: bool
    balance: int
    transaction_id: UUID | None


class WalletService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._wallets = WalletRepository(session)

    async def _get_wallet_for_update(self, wallet_id: UUID) -> Wallet:
        result = await self._session.execute(
            select(Wallet).where(Wallet.id == wallet_id).with_for_update()
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            raise WalletNotFoundError(f"Wallet {wallet_id} not found")
        return wallet

    async def _existing_tx(self, idempotency_key: str) -> CreditTransaction | None:
        return await self._wallets.get_transaction_by_idempotency_key(idempotency_key)

    async def credit(
        self,
        wallet_id: UUID,
        amount: int,
        reason: TxReason | str,
        idempotency_key: str,
        *,
        meta: dict[str, object] | None = None,
    ) -> CreditResult:
        if amount <= 0:
            msg = "Credit amount must be positive"
            raise ValueError(msg)

        existing = await self._existing_tx(idempotency_key)
        if existing is not None:
            return CreditResult(
                applied=False,
                balance=existing.balance_after,
                transaction_id=existing.id,
            )

        wallet = await self._get_wallet_for_update(wallet_id)
        existing = await self._existing_tx(idempotency_key)
        if existing is not None:
            return CreditResult(
                applied=False,
                balance=existing.balance_after,
                transaction_id=existing.id,
            )

        new_balance = wallet.balance + amount
        try:
            async with self._session.begin_nested():
                wallet.balance = new_balance
                wallet.version += 1
                tx = await self._wallets.add_transaction(
                    wallet=wallet,
                    amount=amount,
                    balance_after=new_balance,
                    tx_type=TxType.CREDIT,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    meta=meta,
                )
                await self._session.flush()
        except IntegrityError:
            existing = await self._existing_tx(idempotency_key)
            if existing is not None:
                await self._session.refresh(wallet)
                return CreditResult(
                    applied=False,
                    balance=existing.balance_after,
                    transaction_id=existing.id,
                )
            raise

        return CreditResult(applied=True, balance=new_balance, transaction_id=tx.id)

    async def debit(
        self,
        wallet_id: UUID,
        amount: int,
        reason: TxReason | str,
        idempotency_key: str,
        *,
        meta: dict[str, object] | None = None,
    ) -> CreditResult:
        if amount <= 0:
            msg = "Debit amount must be positive"
            raise ValueError(msg)

        existing = await self._existing_tx(idempotency_key)
        if existing is not None:
            return CreditResult(
                applied=False,
                balance=existing.balance_after,
                transaction_id=existing.id,
            )

        wallet = await self._get_wallet_for_update(wallet_id)
        existing = await self._existing_tx(idempotency_key)
        if existing is not None:
            return CreditResult(
                applied=False,
                balance=existing.balance_after,
                transaction_id=existing.id,
            )

        if wallet.balance < amount:
            raise InsufficientCreditsError(f"Need {amount}, have {wallet.balance}")

        new_balance = wallet.balance - amount
        try:
            async with self._session.begin_nested():
                wallet.balance = new_balance
                wallet.version += 1
                tx = await self._wallets.add_transaction(
                    wallet=wallet,
                    amount=-amount,
                    balance_after=new_balance,
                    tx_type=TxType.DEBIT,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    meta=meta,
                )
                await self._session.flush()
        except IntegrityError:
            existing = await self._existing_tx(idempotency_key)
            if existing is not None:
                await self._session.refresh(wallet)
                return CreditResult(
                    applied=False,
                    balance=existing.balance_after,
                    transaction_id=existing.id,
                )
            raise

        return CreditResult(applied=True, balance=new_balance, transaction_id=tx.id)
