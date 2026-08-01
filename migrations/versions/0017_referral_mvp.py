"""Add immutable referral attribution and ledger-backed reward state.

Revision ID: 0017_referral_mvp
Revises: 0016_image_fallback
Create Date: 2026-08-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_referral_mvp"
down_revision: str | None = "0016_image_fallback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referral_codes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_referral_codes_code", "referral_codes", ["code"], unique=True)
    op.create_index("ix_referral_codes_user_id", "referral_codes", ["user_id"], unique=True)

    op.create_table(
        "referral_attributions",
        sa.Column("referral_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inviter_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invited_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attributed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("inviter_user_id <> invited_user_id", name="ck_referral_no_self"),
        sa.ForeignKeyConstraint(["invited_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inviter_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["referral_code_id"], ["referral_codes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invited_user_id", name="uq_referral_attributions_invited_user"),
    )
    op.create_index("ix_referral_attributions_code", "referral_attributions", ["referral_code_id"])
    op.create_index(
        "ix_referral_attributions_inviter", "referral_attributions", ["inviter_user_id"]
    )
    op.create_index(
        "ix_referral_attributions_invited", "referral_attributions", ["invited_user_id"]
    )

    op.create_table(
        "referral_rewards",
        sa.Column("attribution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("inviter_bonus_credits", sa.Integer(), nullable=False),
        sa.Column("invitee_bonus_credits", sa.Integer(), nullable=False),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inviter_ledger_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invitee_ledger_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_reason", sa.String(length=64), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','eligible','credited','cancelled','needs_review')",
            name="ck_referral_reward_status",
        ),
        sa.CheckConstraint(
            "inviter_bonus_credits >= 0", name="ck_referral_inviter_bonus_nonnegative"
        ),
        sa.CheckConstraint(
            "invitee_bonus_credits >= 0", name="ck_referral_invitee_bonus_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["attribution_id"], ["referral_attributions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["inviter_ledger_transaction_id"],
            ["credit_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invitee_ledger_transaction_id"],
            ["credit_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attribution_id", name="uq_referral_rewards_attribution"),
        sa.UniqueConstraint("payment_order_id", name="uq_referral_rewards_payment_order"),
        sa.UniqueConstraint("inviter_ledger_transaction_id"),
        sa.UniqueConstraint("invitee_ledger_transaction_id"),
    )
    op.create_index("ix_referral_rewards_status", "referral_rewards", ["status"])
    op.create_index("ix_referral_rewards_attribution", "referral_rewards", ["attribution_id"])
    op.create_index("ix_referral_rewards_payment_order", "referral_rewards", ["payment_order_id"])
    op.create_index(
        "ix_referral_rewards_due",
        "referral_rewards",
        ["status", "eligible_at"],
        postgresql_where=sa.text("status = 'eligible'"),
    )

    op.execute(
        """
        CREATE FUNCTION kelbet_referral_attribution_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'referral attribution is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_referral_attribution_immutable
        BEFORE UPDATE OR DELETE ON referral_attributions
        FOR EACH ROW EXECUTE FUNCTION kelbet_referral_attribution_immutable()
        """
    )

    flags = sa.table(
        "feature_flags",
        sa.column("key", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("payload", postgresql.JSONB()),
    )
    statement = postgresql.insert(flags).values(
        [{"key": "referrals", "enabled": False, "payload": {}}]
    )
    op.get_bind().execute(
        statement.on_conflict_do_update(
            index_elements=[flags.c.key],
            set_={"enabled": False, "payload": statement.excluded.payload},
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM feature_flags WHERE key = 'referrals'"))
    op.drop_table("referral_rewards")
    op.execute("DROP FUNCTION IF EXISTS kelbet_referral_attribution_immutable() CASCADE")
    op.drop_table("referral_attributions")
    op.drop_table("referral_codes")
