from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import PaymentOrder, PaymentProduct, PaymentReceipt


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
            select(PaymentReceipt).where(PaymentReceipt.order_id == order_id)
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
