from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import (
    CreditTransaction,
    PaymentOrder,
    PaymentProduct,
    PaymentReceipt,
    PaymentReconciliationIssue,
    PaymentReconciliationRun,
    PaymentRefund,
    StarTransactionObservation,
    Wallet,
)


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_products(self) -> list[PaymentProduct]:
        rows = await self._session.execute(
            select(PaymentProduct)
            .where(PaymentProduct.enabled.is_(True))
            .order_by(PaymentProduct.display_order, PaymentProduct.id)
        )
        return list(rows.scalars().all())

    async def list_products_for_operator(self) -> list[PaymentProduct]:
        rows = await self._session.execute(
            select(PaymentProduct).order_by(PaymentProduct.display_order, PaymentProduct.id)
        )
        return list(rows.scalars().all())

    async def get_product_by_slug(self, slug: str) -> PaymentProduct | None:
        row = await self._session.execute(
            select(PaymentProduct).where(
                PaymentProduct.slug == slug,
                PaymentProduct.enabled.is_(True),
            )
        )
        return row.scalar_one_or_none()

    async def get_order_by_idempotency_key(self, key: str) -> PaymentOrder | None:
        row = await self._session.execute(
            select(PaymentOrder).where(PaymentOrder.idempotency_key == key)
        )
        return row.scalar_one_or_none()

    async def get_order_by_id(
        self, order_id: UUID, *, for_update: bool = False
    ) -> PaymentOrder | None:
        statement = select(PaymentOrder).where(PaymentOrder.id == order_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_order_by_payload(
        self,
        payload: str,
        *,
        for_update: bool = False,
    ) -> PaymentOrder | None:
        statement = select(PaymentOrder).where(PaymentOrder.invoice_payload == payload)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_receipt_by_charge_id(self, charge_id: str) -> PaymentReceipt | None:
        row = await self._session.execute(
            select(PaymentReceipt).where(PaymentReceipt.telegram_payment_charge_id == charge_id)
        )
        return row.scalar_one_or_none()

    async def get_receipt_by_order_id(self, order_id: UUID) -> PaymentReceipt | None:
        row = await self._session.execute(
            select(PaymentReceipt)
            .where(
                PaymentReceipt.order_id == order_id,
                PaymentReceipt.status == "processed",
            )
            .order_by(PaymentReceipt.processed_at.asc().nulls_last(), PaymentReceipt.id)
            .limit(1)
        )
        return row.scalar_one_or_none()

    async def list_orders_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[PaymentOrder]:
        rows = await self._session.execute(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user_id)
            .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all())

    async def list_receipts_for_user(
        self,
        user_id: UUID,
        telegram_id: int,
        *,
        limit: int,
    ) -> list[PaymentReceipt]:
        order_ids = select(PaymentOrder.id).where(PaymentOrder.user_id == user_id)
        rows = await self._session.execute(
            select(PaymentReceipt)
            .where(
                (PaymentReceipt.order_id.in_(order_ids))
                | (PaymentReceipt.telegram_user_id == telegram_id)
            )
            .order_by(PaymentReceipt.created_at.desc(), PaymentReceipt.id.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())

    async def get_product_by_slug_any(self, slug: str) -> PaymentProduct | None:
        row = await self._session.execute(
            select(PaymentProduct).where(PaymentProduct.slug == slug).with_for_update()
        )
        return row.scalar_one_or_none()

    async def get_refund_by_order_id(
        self, order_id: UUID, *, for_update: bool = False
    ) -> PaymentRefund | None:
        statement = select(PaymentRefund).where(PaymentRefund.order_id == order_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_refund_by_id(
        self, refund_id: UUID, *, for_update: bool = False
    ) -> PaymentRefund | None:
        statement = select(PaymentRefund).where(PaymentRefund.id == refund_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_refund_by_charge_id(
        self, charge_id: str, *, for_update: bool = False
    ) -> PaymentRefund | None:
        statement = select(PaymentRefund).where(PaymentRefund.payment_charge_id == charge_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_refund_by_reference(self, reference: str) -> PaymentRefund | None:
        row = await self._session.execute(
            select(PaymentRefund).where(PaymentRefund.operator_reference == reference)
        )
        return row.scalar_one_or_none()

    async def count_refunds_since(
        self,
        since: datetime,
        *,
        telegram_user_id: int | None = None,
        operator_user_id: UUID | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(PaymentRefund)
            .where(PaymentRefund.requested_at >= since)
        )
        if telegram_user_id is not None:
            statement = statement.where(PaymentRefund.telegram_user_id == telegram_user_id)
        if operator_user_id is not None:
            statement = statement.where(PaymentRefund.operator_user_id == operator_user_id)
        return int((await self._session.execute(statement)).scalar_one())

    async def claim_due_refund(self, now: datetime) -> PaymentRefund | None:
        row = await self._session.execute(
            select(PaymentRefund)
            .where(
                PaymentRefund.status.in_(["requested", "failed"]),
                (PaymentRefund.next_attempt_at.is_(None)) | (PaymentRefund.next_attempt_at <= now),
            )
            .order_by(PaymentRefund.requested_at, PaymentRefund.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return row.scalar_one_or_none()

    async def claim_stale_processing_refund(self, stale_before: datetime) -> PaymentRefund | None:
        row = await self._session.execute(
            select(PaymentRefund)
            .where(
                PaymentRefund.status == "processing",
                PaymentRefund.processing_started_at <= stale_before,
            )
            .order_by(PaymentRefund.processing_started_at, PaymentRefund.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return row.scalar_one_or_none()

    async def list_refunds(self, *, limit: int, offset: int) -> list[PaymentRefund]:
        rows = await self._session.execute(
            select(PaymentRefund)
            .order_by(PaymentRefund.requested_at.desc(), PaymentRefund.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all())

    async def get_observation(
        self, transaction_id: str, direction: str
    ) -> StarTransactionObservation | None:
        row = await self._session.execute(
            select(StarTransactionObservation).where(
                StarTransactionObservation.telegram_transaction_id == transaction_id,
                StarTransactionObservation.direction == direction,
            )
        )
        return row.scalar_one_or_none()

    async def list_observations(self) -> list[StarTransactionObservation]:
        rows = await self._session.execute(select(StarTransactionObservation))
        return list(rows.scalars().all())

    async def list_paid_orders(self) -> list[PaymentOrder]:
        rows = await self._session.execute(
            select(PaymentOrder).where(PaymentOrder.status == "paid")
        )
        return list(rows.scalars().all())

    async def get_first_paid_order_for_user(self, user_id: UUID) -> PaymentOrder | None:
        row = await self._session.execute(
            select(PaymentOrder)
            .where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.status == "paid",
            )
            .order_by(
                PaymentOrder.paid_at.asc().nulls_last(),
                PaymentOrder.created_at.asc(),
                PaymentOrder.id.asc(),
            )
            .limit(1)
        )
        return row.scalar_one_or_none()

    async def list_payment_purchase_transactions(self) -> list[CreditTransaction]:
        rows = await self._session.execute(
            select(CreditTransaction)
            .join(Wallet, Wallet.id == CreditTransaction.wallet_id)
            .where(CreditTransaction.reason == "payment_purchase")
        )
        return list(rows.scalars().all())

    async def get_issue(self, issue_key: str) -> PaymentReconciliationIssue | None:
        row = await self._session.execute(
            select(PaymentReconciliationIssue).where(
                PaymentReconciliationIssue.issue_key == issue_key
            )
        )
        return row.scalar_one_or_none()

    async def list_issues(
        self, *, status: str | None, limit: int, offset: int
    ) -> list[PaymentReconciliationIssue]:
        statement = select(PaymentReconciliationIssue)
        if status is not None:
            statement = statement.where(PaymentReconciliationIssue.status == status)
        rows = await self._session.execute(
            statement.order_by(
                PaymentReconciliationIssue.last_seen_at.desc(),
                PaymentReconciliationIssue.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all())

    async def list_open_issues(self) -> list[PaymentReconciliationIssue]:
        rows = await self._session.execute(
            select(PaymentReconciliationIssue).where(
                PaymentReconciliationIssue.status.in_(["open", "needs_review"])
            )
        )
        return list(rows.scalars().all())

    async def latest_reconciliation_run(self) -> PaymentReconciliationRun | None:
        row = await self._session.execute(
            select(PaymentReconciliationRun)
            .order_by(PaymentReconciliationRun.started_at.desc())
            .limit(1)
        )
        return row.scalar_one_or_none()
