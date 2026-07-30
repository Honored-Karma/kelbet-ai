from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentProduct(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payment_products"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    localization: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class PaymentOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payment_orders"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    invoice_payload: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="XTR")
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    product_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    terms_version: Mapped[str] = mapped_column(String(32), nullable=False)
    terms_accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    pre_checkout_query_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    ledger_transaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentReceipt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "payment_receipts"
    __table_args__ = (UniqueConstraint("order_id", name="uq_payment_receipts_order_id"),)

    order_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    telegram_payment_charge_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invoice_payload: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
