from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
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
        unique=True,
    )
    pre_checkout_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pre_checkout_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_invoice_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invoice_open_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
    __table_args__ = (
        Index(
            "uq_payment_receipts_processed_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'processed'"),
        ),
    )

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


class PaymentRefund(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payment_refunds"

    order_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    receipt_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_receipts.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    payment_charge_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    operator_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operator_reference: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stars_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ledger_transaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StarTransactionObservation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "star_transaction_observations"
    __table_args__ = (
        UniqueConstraint(
            "telegram_transaction_id",
            "direction",
            name="uq_star_transaction_observation_identity",
        ),
    )

    telegram_transaction_id: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    partner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    invoice_payload: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentReconciliationRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "payment_reconciliation_runs"

    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PaymentReconciliationIssue(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "payment_reconciliation_issues"

    issue_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    order_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_orders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    refund_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_refunds.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    telegram_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
