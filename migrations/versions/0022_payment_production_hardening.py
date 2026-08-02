"""Harden Telegram Stars checkout, recovery, and reconciliation coverage.

Revision ID: 0022_payment_production_hardening
Revises: 0021_veo_extended_workflow
Create Date: 2026-08-02 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_payment_production_hardening"
down_revision: str | None = "0021_veo_extended_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_orders",
        sa.Column("pre_checkout_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_orders",
        sa.Column("pre_checkout_telegram_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "payment_orders",
        sa.Column("last_invoice_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_orders",
        sa.Column("invoice_open_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_unique_constraint(
        "uq_payment_orders_pre_checkout_query_id",
        "payment_orders",
        ["pre_checkout_query_id"],
    )

    op.drop_constraint("uq_payment_receipts_order_id", "payment_receipts", type_="unique")
    op.create_index(
        "uq_payment_receipts_processed_order",
        "payment_receipts",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'processed'"),
    )

    op.add_column(
        "star_transaction_observations",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "star_transaction_observations",
        sa.Column("invoice_payload", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_star_transaction_observations_telegram_user_id",
        "star_transaction_observations",
        ["telegram_user_id"],
    )
    op.create_index(
        "ix_star_transaction_observations_invoice_payload",
        "star_transaction_observations",
        ["invoice_payload"],
    )

    op.add_column(
        "payment_reconciliation_runs",
        sa.Column("coverage_complete", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "payment_reconciliation_runs",
        sa.Column("next_offset", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_reconciliation_runs", "next_offset")
    op.drop_column("payment_reconciliation_runs", "coverage_complete")
    op.drop_index(
        "ix_star_transaction_observations_invoice_payload",
        table_name="star_transaction_observations",
    )
    op.drop_index(
        "ix_star_transaction_observations_telegram_user_id",
        table_name="star_transaction_observations",
    )
    op.drop_column("star_transaction_observations", "invoice_payload")
    op.drop_column("star_transaction_observations", "telegram_user_id")
    op.drop_index("uq_payment_receipts_processed_order", table_name="payment_receipts")

    # Restoring the unconditional unique constraint is only possible while every
    # order still has at most one receipt. After a duplicate Stars charge the
    # rejected receipt legitimately shares its order_id, and recreating the old
    # constraint would abort mid-downgrade with a bare UniqueViolation. Fail
    # early with an actionable message instead of a cryptic driver error.
    duplicate_order = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT order_id FROM payment_receipts "
                "GROUP BY order_id HAVING count(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicate_order is not None:
        raise RuntimeError(
            "Cannot restore uq_payment_receipts_order_id: payment_receipts holds "
            f"multiple receipts for order {duplicate_order[0]}. This is expected "
            "after a duplicate Stars charge. Resolve or archive the extra receipts "
            "before downgrading past 0022 — see "
            "docs/architecture/PAYMENT_BACKUP_RESTORE_RUNBOOK.md."
        )

    op.create_unique_constraint("uq_payment_receipts_order_id", "payment_receipts", ["order_id"])
    op.drop_constraint("uq_payment_orders_pre_checkout_query_id", "payment_orders", type_="unique")
    op.drop_column("payment_orders", "invoice_open_count")
    op.drop_column("payment_orders", "last_invoice_opened_at")
    op.drop_column("payment_orders", "pre_checkout_telegram_id")
    op.drop_column("payment_orders", "pre_checkout_claimed_at")
