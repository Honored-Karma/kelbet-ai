"""Add wallets.reserved and credit_reservations (soft-hold).

Revision ID: 0002_wallet_reserved
Revises: 0001_initial
Create Date: 2026-07-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_wallet_reserved"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column("reserved", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_wallets_reserved_non_negative",
        "wallets",
        "reserved >= 0",
    )
    op.create_check_constraint(
        "ck_wallets_balance_gte_reserved",
        "wallets",
        "balance >= reserved",
    )

    op.create_table(
        "credit_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("quote_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capture_tx_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("refund_tx_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_credit_reservations_amount_positive")),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["wallets.id"],
            name=op.f("fk_credit_reservations_wallet_id_wallets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_credit_reservations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["capture_tx_id"],
            ["credit_transactions.id"],
            name=op.f("fk_credit_reservations_capture_tx_id_credit_transactions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["refund_tx_id"],
            ["credit_transactions.id"],
            name=op.f("fk_credit_reservations_refund_tx_id_credit_transactions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_reservations")),
        sa.UniqueConstraint(
            "idempotency_key",
            name=op.f("uq_credit_reservations_idempotency_key"),
        ),
    )
    op.create_index(
        op.f("ix_credit_reservations_wallet_id"),
        "credit_reservations",
        ["wallet_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_reservations_user_id"),
        "credit_reservations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_reservations_generation_id"),
        "credit_reservations",
        ["generation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_credit_reservations_generation_id"), table_name="credit_reservations")
    op.drop_index(op.f("ix_credit_reservations_user_id"), table_name="credit_reservations")
    op.drop_index(op.f("ix_credit_reservations_wallet_id"), table_name="credit_reservations")
    op.drop_table("credit_reservations")
    op.drop_constraint("ck_wallets_balance_gte_reserved", "wallets", type_="check")
    op.drop_constraint("ck_wallets_reserved_non_negative", "wallets", type_="check")
    op.drop_column("wallets", "reserved")
