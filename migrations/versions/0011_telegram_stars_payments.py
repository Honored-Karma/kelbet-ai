"""Add Telegram Stars products, orders, and durable receipts.

Revision ID: 0011_telegram_stars_payments
Revises: 0010_video_mvp
Create Date: 2026-07-30 23:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.payments import payment_product_rows

revision: str = "0011_telegram_stars_payments"
down_revision: str | None = "0010_video_mvp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_products",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("localization", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("credits > 0", name="payment_product_credits_positive"),
        sa.CheckConstraint("stars > 0", name="payment_product_stars_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "payment_orders",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("invoice_payload", sa.String(length=128), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("product_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("terms_version", sa.String(length=32), nullable=False),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pre_checkout_query_id", sa.String(length=128), nullable=True),
        sa.Column("ledger_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("credits > 0", name="payment_order_credits_positive"),
        sa.CheckConstraint("total_amount > 0", name="payment_order_total_positive"),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"], ["credit_transactions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["payment_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("invoice_payload"),
        sa.UniqueConstraint("ledger_transaction_id"),
    )
    op.create_index("ix_payment_orders_status", "payment_orders", ["status"])
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_table(
        "payment_receipts",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_payment_charge_id", sa.String(length=128), nullable=False),
        sa.Column("provider_payment_charge_id", sa.String(length=128), nullable=True),
        sa.Column("invoice_payload", sa.String(length=128), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("total_amount > 0", name="payment_receipt_total_positive"),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_payment_receipts_order_id"),
        sa.UniqueConstraint("telegram_payment_charge_id"),
    )
    op.create_index(
        "ix_payment_receipts_status",
        "payment_receipts",
        ["status"],
    )
    op.create_index(
        "ix_payment_receipts_telegram_user_id",
        "payment_receipts",
        ["telegram_user_id"],
    )

    products = sa.table(
        "payment_products",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String()),
        sa.column("credits", sa.Integer()),
        sa.column("stars", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("display_order", sa.Integer()),
        sa.column("localization", postgresql.JSONB()),
    )
    op.bulk_insert(products, payment_product_rows())


def downgrade() -> None:
    op.drop_index("ix_payment_receipts_telegram_user_id", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_status", table_name="payment_receipts")
    op.drop_table("payment_receipts")
    op.drop_index("ix_payment_orders_user_id", table_name="payment_orders")
    op.drop_index("ix_payment_orders_status", table_name="payment_orders")
    op.drop_table("payment_orders")
    op.drop_table("payment_products")
