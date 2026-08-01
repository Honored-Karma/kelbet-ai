"""Add recoverable Telegram Stars refunds and reconciliation state.

Revision ID: 0015_stars_refunds
Revises: 0014_generation_templates
Create Date: 2026-08-01 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_stars_refunds"
down_revision: str | None = "0014_generation_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_refunds",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_charge_id", sa.String(length=128), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("operator_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_reference", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stars_amount", sa.Integer(), nullable=False),
        sa.Column("credits_amount", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ledger_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("stars_amount > 0", name="payment_refund_stars_positive"),
        sa.CheckConstraint("credits_amount > 0", name="payment_refund_credits_positive"),
        sa.CheckConstraint("attempt_count >= 0", name="payment_refund_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('requested','processing','refunded','failed','needs_review')",
            name="payment_refund_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"], ["credit_transactions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_id"], ["payment_receipts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_transaction_id"),
        sa.UniqueConstraint("operator_reference"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("payment_charge_id"),
        sa.UniqueConstraint("receipt_id"),
    )
    op.create_index("ix_payment_refunds_operator_user_id", "payment_refunds", ["operator_user_id"])
    op.create_index("ix_payment_refunds_status", "payment_refunds", ["status"])
    op.create_index("ix_payment_refunds_telegram_user_id", "payment_refunds", ["telegram_user_id"])

    op.create_table(
        "star_transaction_observations",
        sa.Column("telegram_transaction_id", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("partner_type", sa.String(length=32), nullable=False),
        sa.Column("transaction_type", sa.String(length=64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="star_transaction_amount_positive"),
        sa.CheckConstraint(
            "direction IN ('incoming','outgoing')", name="star_transaction_direction_valid"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "telegram_transaction_id",
            "direction",
            name="uq_star_transaction_observation_identity",
        ),
    )
    op.create_index(
        "ix_star_transaction_observations_direction",
        "star_transaction_observations",
        ["direction"],
    )

    op.create_table(
        "payment_reconciliation_runs",
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fetched_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("issue_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','completed','failed')",
            name="payment_reconciliation_run_status_valid",
        ),
        sa.CheckConstraint("fetched_count >= 0", name="reconciliation_fetched_nonnegative"),
        sa.CheckConstraint("issue_count >= 0", name="reconciliation_issues_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payment_reconciliation_runs_status", "payment_reconciliation_runs", ["status"]
    )

    op.create_table(
        "payment_reconciliation_issues",
        sa.Column("issue_key", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("refund_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("telegram_transaction_id", sa.String(length=128), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open','resolved','needs_review')",
            name="payment_reconciliation_issue_status_valid",
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="payment_reconciliation_issue_severity_valid",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["refund_id"], ["payment_refunds.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_key"),
    )
    op.create_index(
        "ix_payment_reconciliation_issues_kind", "payment_reconciliation_issues", ["kind"]
    )
    op.create_index(
        "ix_payment_reconciliation_issues_order_id",
        "payment_reconciliation_issues",
        ["order_id"],
    )
    op.create_index(
        "ix_payment_reconciliation_issues_refund_id",
        "payment_reconciliation_issues",
        ["refund_id"],
    )
    op.create_index(
        "ix_payment_reconciliation_issues_status", "payment_reconciliation_issues", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_reconciliation_issues_status", table_name="payment_reconciliation_issues"
    )
    op.drop_index(
        "ix_payment_reconciliation_issues_refund_id", table_name="payment_reconciliation_issues"
    )
    op.drop_index(
        "ix_payment_reconciliation_issues_order_id", table_name="payment_reconciliation_issues"
    )
    op.drop_index(
        "ix_payment_reconciliation_issues_kind", table_name="payment_reconciliation_issues"
    )
    op.drop_table("payment_reconciliation_issues")
    op.drop_index("ix_payment_reconciliation_runs_status", table_name="payment_reconciliation_runs")
    op.drop_table("payment_reconciliation_runs")
    op.drop_index(
        "ix_star_transaction_observations_direction",
        table_name="star_transaction_observations",
    )
    op.drop_table("star_transaction_observations")
    op.drop_index("ix_payment_refunds_telegram_user_id", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_status", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_operator_user_id", table_name="payment_refunds")
    op.drop_table("payment_refunds")
