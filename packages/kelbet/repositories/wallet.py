from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import CreditReservation, CreditTransaction, Wallet
from kelbet.domain.enums import ReservationStatus, TxReason, TxType


class WalletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> Wallet | None:
        result = await self._session.execute(select(Wallet).where(Wallet.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_user_id_for_update(self, user_id: UUID) -> Wallet | None:
        result = await self._session.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, wallet_id: UUID) -> Wallet | None:
        result = await self._session.execute(select(Wallet).where(Wallet.id == wallet_id))
        return result.scalar_one_or_none()

    async def create(self, user_id: UUID) -> Wallet:
        wallet = Wallet(user_id=user_id, balance=0, reserved=0, version=0)
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

    async def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> CreditReservation | None:
        result = await self._session.execute(
            select(CreditReservation).where(CreditReservation.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def get_reservation_by_id(self, reservation_id: UUID) -> CreditReservation | None:
        result = await self._session.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
        )
        return result.scalar_one_or_none()

    async def list_expired_held_reservations(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> list[CreditReservation]:
        """Holds whose deadline has passed and which nobody has finalised.

        Oldest first, so a backlog drains in the order it accumulated. Locked
        with skip_locked because the sweeper may run alongside the runner
        finalising the very same reservation.
        """

        result = await self._session.execute(
            select(CreditReservation)
            .where(
                CreditReservation.status == ReservationStatus.HELD.value,
                CreditReservation.expires_at <= now,
            )
            .order_by(CreditReservation.expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

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

    async def add_reservation(
        self,
        *,
        wallet_id: UUID,
        user_id: UUID,
        amount: int,
        idempotency_key: str,
        quote_snapshot: dict[str, Any],
        expires_at: datetime,
        held_at: datetime,
    ) -> CreditReservation:
        reservation = CreditReservation(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            status=ReservationStatus.HELD.value,
            idempotency_key=idempotency_key,
            quote_snapshot=quote_snapshot,
            expires_at=expires_at,
            held_at=held_at,
        )
        self._session.add(reservation)
        await self._session.flush()
        return reservation

    async def count_transactions(self, wallet_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.wallet_id == wallet_id)
        )
        return int(result.scalar_one())

    async def list_transactions(
        self,
        wallet_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreditTransaction]:
        result = await self._session.execute(
            select(CreditTransaction)
            .where(CreditTransaction.wallet_id == wallet_id)
            .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
