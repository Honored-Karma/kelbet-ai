from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import CreditReservation, CreditTransaction, Wallet
from kelbet.domain.enums import ReservationStatus, TxReason, TxType
from kelbet.domain.exceptions import (
    InsufficientCreditsError,
    InvalidReservationStateError,
    ReservationNotFoundError,
    WalletNotFoundError,
)
from kelbet.observability import get_metrics
from kelbet.repositories.wallet import WalletRepository

# Credits are captured when the job finishes, so this TTL has to outlast the
# longest job budget — an extended Veo chain alone is allowed a full hour
# (veo_extended_total_timeout_seconds). At the previous one hour the expiry and
# the job deadline fell on the same instant, so enforcing expiry would have
# raced legitimately running work and released credits from under it.
DEFAULT_RESERVATION_TTL = timedelta(hours=6)


def _record_wallet_operation(operation: str, *, applied: bool) -> None:
    get_metrics().incr(
        "wallet.operation",
        tags={"operation": operation, "outcome": "applied" if applied else "idempotent"},
    )


@dataclass(frozen=True, slots=True)
class CreditResult:
    applied: bool
    balance: int
    transaction_id: UUID | None


@dataclass(frozen=True, slots=True)
class ReservationResult:
    applied: bool
    reservation_id: UUID
    amount: int
    status: ReservationStatus
    balance: int
    reserved: int
    available: int
    capture_tx_id: UUID | None = None
    refund_tx_id: UUID | None = None


def capture_idempotency_key(reservation_id: UUID) -> str:
    return f"capture:{reservation_id}"


def refund_idempotency_key(reservation_id: UUID) -> str:
    return f"refund:{reservation_id}"


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

    async def _get_reservation_for_update(self, reservation_id: UUID) -> CreditReservation:
        result = await self._session.execute(
            select(CreditReservation)
            .where(CreditReservation.id == reservation_id)
            .with_for_update()
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return reservation

    async def _get_reservation_by_key(self, idempotency_key: str) -> CreditReservation | None:
        return await self._wallets.get_reservation_by_idempotency_key(idempotency_key)

    def _reservation_result(
        self,
        *,
        applied: bool,
        reservation: CreditReservation,
        wallet: Wallet,
    ) -> ReservationResult:
        return ReservationResult(
            applied=applied,
            reservation_id=reservation.id,
            amount=reservation.amount,
            status=ReservationStatus(reservation.status),
            balance=wallet.balance,
            reserved=wallet.reserved,
            available=wallet.balance - wallet.reserved,
            capture_tx_id=reservation.capture_tx_id,
            refund_tx_id=reservation.refund_tx_id,
        )

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

        available = wallet.balance - wallet.reserved
        if available < amount:
            raise InsufficientCreditsError(f"Need {amount}, have {available} available")

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

    async def reserve(
        self,
        wallet_id: UUID,
        amount: int,
        idempotency_key: str,
        *,
        user_id: UUID,
        quote_snapshot: dict[str, Any] | None = None,
        ttl: timedelta = DEFAULT_RESERVATION_TTL,
        now: datetime | None = None,
    ) -> ReservationResult:
        if amount <= 0:
            msg = "Reserve amount must be positive"
            raise ValueError(msg)

        existing = await self._get_reservation_by_key(idempotency_key)
        if existing is not None:
            wallet = await self._wallets.get_by_id(existing.wallet_id)
            if wallet is None:
                raise WalletNotFoundError(f"Wallet {existing.wallet_id} not found")
            result = self._reservation_result(applied=False, reservation=existing, wallet=wallet)
            _record_wallet_operation("reserve", applied=False)
            return result

        held_at = now or datetime.now(UTC)
        expires_at = held_at + ttl

        wallet = await self._get_wallet_for_update(wallet_id)
        existing = await self._get_reservation_by_key(idempotency_key)
        if existing is not None:
            result = self._reservation_result(applied=False, reservation=existing, wallet=wallet)
            _record_wallet_operation("reserve", applied=False)
            return result

        available = wallet.balance - wallet.reserved
        if available < amount:
            raise InsufficientCreditsError(f"Need {amount}, have {available} available")

        try:
            async with self._session.begin_nested():
                wallet.reserved += amount
                wallet.version += 1
                reservation = await self._wallets.add_reservation(
                    wallet_id=wallet.id,
                    user_id=user_id,
                    amount=amount,
                    idempotency_key=idempotency_key,
                    quote_snapshot=quote_snapshot or {},
                    expires_at=expires_at,
                    held_at=held_at,
                )
                await self._session.flush()
        except IntegrityError:
            existing = await self._get_reservation_by_key(idempotency_key)
            if existing is not None:
                await self._session.refresh(wallet)
                result = self._reservation_result(
                    applied=False, reservation=existing, wallet=wallet
                )
                _record_wallet_operation("reserve", applied=False)
                return result
            raise

        result = self._reservation_result(applied=True, reservation=reservation, wallet=wallet)
        _record_wallet_operation("reserve", applied=True)
        return result

    async def capture(
        self,
        reservation_id: UUID,
        *,
        meta: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> ReservationResult:
        reservation = await self._get_reservation_for_update(reservation_id)
        wallet = await self._get_wallet_for_update(reservation.wallet_id)
        finalized_at = now or datetime.now(UTC)

        if reservation.status == ReservationStatus.CAPTURED.value:
            result = self._reservation_result(applied=False, reservation=reservation, wallet=wallet)
            _record_wallet_operation("capture", applied=False)
            return result

        if reservation.status != ReservationStatus.HELD.value:
            raise InvalidReservationStateError(
                f"Cannot capture reservation {reservation_id} in status {reservation.status}"
            )

        amount = reservation.amount
        if wallet.reserved < amount:
            raise InvalidReservationStateError(
                f"Wallet reserved {wallet.reserved} < reservation amount {amount}"
            )
        if wallet.balance < amount:
            raise InsufficientCreditsError(f"Need {amount}, have {wallet.balance}")

        idem_key = capture_idempotency_key(reservation.id)
        existing_tx = await self._existing_tx(idem_key)
        if existing_tx is not None:
            reservation.status = ReservationStatus.CAPTURED.value
            reservation.capture_tx_id = existing_tx.id
            reservation.finalized_at = reservation.finalized_at or finalized_at
            await self._session.flush()
            result = self._reservation_result(applied=False, reservation=reservation, wallet=wallet)
            _record_wallet_operation("capture", applied=False)
            return result

        new_balance = wallet.balance - amount
        new_reserved = wallet.reserved - amount
        try:
            async with self._session.begin_nested():
                wallet.balance = new_balance
                wallet.reserved = new_reserved
                wallet.version += 1
                tx = await self._wallets.add_transaction(
                    wallet=wallet,
                    amount=-amount,
                    balance_after=new_balance,
                    tx_type=TxType.DEBIT,
                    reason=TxReason.GENERATION_CAPTURE,
                    idempotency_key=idem_key,
                    meta={
                        **(meta or {}),
                        "reservation_id": str(reservation.id),
                        "source": "generation_capture",
                    },
                )
                reservation.status = ReservationStatus.CAPTURED.value
                reservation.capture_tx_id = tx.id
                reservation.finalized_at = finalized_at
                await self._session.flush()
        except IntegrityError:
            existing_tx = await self._existing_tx(idem_key)
            if existing_tx is not None:
                await self._session.refresh(wallet)
                await self._session.refresh(reservation)
                if reservation.status != ReservationStatus.CAPTURED.value:
                    reservation.status = ReservationStatus.CAPTURED.value
                    reservation.capture_tx_id = existing_tx.id
                    reservation.finalized_at = reservation.finalized_at or finalized_at
                    await self._session.flush()
                result = self._reservation_result(
                    applied=False, reservation=reservation, wallet=wallet
                )
                _record_wallet_operation("capture", applied=False)
                return result
            raise

        result = self._reservation_result(applied=True, reservation=reservation, wallet=wallet)
        _record_wallet_operation("capture", applied=True)
        return result

    async def release(
        self,
        reservation_id: UUID,
        *,
        now: datetime | None = None,
    ) -> ReservationResult:
        return await self._unhold(
            reservation_id,
            target=ReservationStatus.RELEASED,
            operation="release",
            now=now,
        )

    async def expire(
        self,
        reservation_id: UUID,
        *,
        now: datetime | None = None,
    ) -> ReservationResult:
        """Return a hold whose deadline passed with nothing left to capture it.

        The wallet effect is identical to a release — the balance was never
        debited — but the status is kept apart so that credits handed back by a
        deadline stay distinguishable from credits handed back by a job that
        reached a terminal state on its own.
        """

        return await self._unhold(
            reservation_id,
            target=ReservationStatus.EXPIRED,
            operation="expire",
            now=now,
        )

    async def _unhold(
        self,
        reservation_id: UUID,
        *,
        target: ReservationStatus,
        operation: str,
        now: datetime | None = None,
    ) -> ReservationResult:
        reservation = await self._get_reservation_for_update(reservation_id)
        wallet = await self._get_wallet_for_update(reservation.wallet_id)
        finalized_at = now or datetime.now(UTC)

        # Released and expired are both already-unheld outcomes, so arriving at
        # either from either direction is idempotent rather than an error: a
        # sweep racing the runner must not raise on work the runner finished.
        if reservation.status in {
            ReservationStatus.RELEASED.value,
            ReservationStatus.EXPIRED.value,
        }:
            result = self._reservation_result(applied=False, reservation=reservation, wallet=wallet)
            _record_wallet_operation(operation, applied=False)
            return result

        if reservation.status != ReservationStatus.HELD.value:
            raise InvalidReservationStateError(
                f"Cannot {operation} reservation {reservation_id} in status {reservation.status}"
            )

        amount = reservation.amount
        if wallet.reserved < amount:
            raise InvalidReservationStateError(
                f"Wallet reserved {wallet.reserved} < reservation amount {amount}"
            )

        wallet.reserved -= amount
        wallet.version += 1
        reservation.status = target.value
        reservation.finalized_at = finalized_at
        await self._session.flush()

        result = self._reservation_result(applied=True, reservation=reservation, wallet=wallet)
        _record_wallet_operation(operation, applied=True)
        return result

    async def refund(
        self,
        reservation_id: UUID,
        *,
        meta: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> ReservationResult:
        """Refund after capture. Idempotent via ledger key refund:{reservation_id}."""
        reservation = await self._get_reservation_for_update(reservation_id)
        wallet = await self._get_wallet_for_update(reservation.wallet_id)
        finalized_at = now or datetime.now(UTC)

        if reservation.refund_tx_id is not None:
            result = self._reservation_result(applied=False, reservation=reservation, wallet=wallet)
            _record_wallet_operation("refund", applied=False)
            return result

        if reservation.status != ReservationStatus.CAPTURED.value:
            raise InvalidReservationStateError(
                f"Cannot refund reservation {reservation_id} in status {reservation.status}"
            )

        amount = reservation.amount
        idem_key = refund_idempotency_key(reservation.id)
        existing_tx = await self._existing_tx(idem_key)
        if existing_tx is not None:
            reservation.refund_tx_id = existing_tx.id
            await self._session.flush()
            result = self._reservation_result(applied=False, reservation=reservation, wallet=wallet)
            _record_wallet_operation("refund", applied=False)
            return result

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
                    reason=TxReason.GENERATION_REFUND,
                    idempotency_key=idem_key,
                    meta={
                        **(meta or {}),
                        "reservation_id": str(reservation.id),
                        "source": "generation_refund",
                    },
                )
                reservation.refund_tx_id = tx.id
                if reservation.finalized_at is None:
                    reservation.finalized_at = finalized_at
                await self._session.flush()
        except IntegrityError:
            existing_tx = await self._existing_tx(idem_key)
            if existing_tx is not None:
                await self._session.refresh(wallet)
                await self._session.refresh(reservation)
                reservation.refund_tx_id = existing_tx.id
                await self._session.flush()
                result = self._reservation_result(
                    applied=False, reservation=reservation, wallet=wallet
                )
                _record_wallet_operation("refund", applied=False)
                return result
            raise

        result = self._reservation_result(applied=True, reservation=reservation, wallet=wallet)
        _record_wallet_operation("refund", applied=True)
        return result
