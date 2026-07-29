from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import CreditTransaction, Wallet
from kelbet.domain.enums import TxReason, TxType


class WalletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> Wallet | None:
        result = await self._session.execute(select(Wallet).where(Wallet.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, wallet_id: UUID) -> Wallet | None:
        result = await self._session.execute(select(Wallet).where(Wallet.id == wallet_id))
        return result.scalar_one_or_none()

    async def create(self, user_id: UUID) -> Wallet:
        wallet = Wallet(user_id=user_id, balance=0, version=0)
        self._session.add(wallet)
        await self._session.flush()
        return wallet

    async def get_transaction_by_idempotency_key(
        self, idempotency_key: str
    ) -> CreditTransaction | None:
        result = await self._session.execute(
            select(CreditTransaction).where(CreditTransaction.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def add_transaction(
        self,
        *,
        wallet: Wallet,
        amount: int,
        balance_after: int,
        tx_type: TxType,
        reason: TxReason | str,
        idempotency_key: str,
        meta: dict[str, object] | None = None,
    ) -> CreditTransaction:
        reason_value = reason.value if isinstance(reason, TxReason) else reason
        tx = CreditTransaction(
            wallet_id=wallet.id,
            amount=amount,
            balance_after=balance_after,
            type=tx_type.value,
            reason=reason_value,
            idempotency_key=idempotency_key,
            meta=meta,
        )
        self._session.add(tx)
        await self._session.flush()
        return tx

    async def count_transactions(self, wallet_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.wallet_id == wallet_id)
        )
        return int(result.scalar_one())
