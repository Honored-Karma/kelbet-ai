"""Add recurring Telegram Stars subscriptions.

Revision ID: 0023_subscriptions
Revises: 0022_payment_hardening
Create Date: 2026-08-03 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.subscriptions import subscription_plan_rows

revision: str = "0023_subscriptions"
down_revision: str | None = "0022_payment_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Non-terminal states. A user may accumulate history but hold only one live subscription.
_LIVE_STATUSES = "'pending', 'active', 'cancelled', 'payment_failed'"


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("monthly_credits", sa.Integer(), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("kzt_price", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("localization", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("monthly_credits > 0", name="subscription_plan_credits_positive"),
        sa.CheckConstraint("stars > 0", name="subscription_plan_stars_positive"),
        sa.CheckConstraint(
            "kzt_price is null or kzt_price > 0", name="subscription_plan_kzt_price_positive"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_plans")),
        sa.UniqueConstraint("slug", name=op.f("uq_subscription_plans_slug")),
        sa.UniqueConstraint("plan", name=op.f("uq_subscription_plans_plan")),
    )

    op.create_table(
        "subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("plan_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("invoice_payload", sa.String(length=128), nullable=False),
        sa.Column("root_charge_id", sa.String(length=128), nullable=True),
        sa.Column("terms_version", sa.String(length=32), nullable=False),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewal_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewal_count", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["subscription_plans.id"],
            name=op.f("fk_subscriptions_plan_id_subscription_plans"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_subscriptions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("invoice_payload", name=op.f("uq_subscriptions_invoice_payload")),
        sa.UniqueConstraint("root_charge_id", name=op.f("uq_subscriptions_root_charge_id")),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_current_period_end", "subscriptions", ["current_period_end"])
    op.create_index("ix_subscriptions_root_charge_id", "subscriptions", ["root_charge_id"])
    # One live subscription per user. A partial index rather than a plain unique
    # constraint, so expired history does not block a user from resubscribing.
    op.create_index(
        "uq_subscriptions_live_per_user",
        "subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text(f"status in ({_LIVE_STATUSES})"),
    )

    op.create_table(
        "subscription_periods",
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("charge_id", sa.String(length=128), nullable=False),
        sa.Column("provider_charge_id", sa.String(length=128), nullable=True),
        sa.Column("stars_amount", sa.Integer(), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("is_first", sa.Boolean(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ledger_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"],
            ["credit_transactions.id"],
            name=op.f("fk_subscription_periods_ledger_transaction_id_credit_transactions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_subscription_periods_subscription_id_subscriptions"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("credits_granted > 0", name="subscription_period_credits_positive"),
        sa.CheckConstraint("stars_amount > 0", name="subscription_period_stars_positive"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_periods")),
        # The charge id is the exactly-once key for granting a period's credits.
        sa.UniqueConstraint("charge_id", name=op.f("uq_subscription_periods_charge_id")),
        sa.UniqueConstraint(
            "ledger_transaction_id",
            name=op.f("uq_subscription_periods_ledger_transaction_id"),
        ),
    )
    op.create_index(
        "ix_subscription_periods_subscription_id", "subscription_periods", ["subscription_id"]
    )

    # Seeding through the migration follows the convention set by 0011 for payment products:
    # a deployment that runs migrations has the tiers available without a separate step.
    # Prices stay editable afterwards, and a live subscription reads its own frozen snapshot,
    # so later edits never change what an existing subscriber pays.
    plans = sa.table(
        "subscription_plans",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String()),
        sa.column("plan", sa.String()),
        sa.column("monthly_credits", sa.Integer()),
        sa.column("stars", sa.Integer()),
        sa.column("kzt_price", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("display_order", sa.Integer()),
        sa.column("localization", postgresql.JSONB()),
    )
    op.bulk_insert(plans, subscription_plan_rows())


def downgrade() -> None:
    op.drop_index("ix_subscription_periods_subscription_id", table_name="subscription_periods")
    op.drop_table("subscription_periods")
    op.drop_index("uq_subscriptions_live_per_user", table_name="subscriptions")
    op.drop_index("ix_subscriptions_root_charge_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_current_period_end", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
