"""Add recurring subscription plans, per-user subscriptions, and grant ledger.

Revision ID: 0023_subscriptions
Revises: 0022_payment_hardening
Create Date: 2026-08-03 18:00:00.000000

The `subscriptions` feature flag ships disabled. UNIQUE(subscription_id, period_index)
on subscription_grants is the storage-level guarantee that a replayed renewal cannot
credit a second period, independently of any service check.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.subscriptions.seeds import subscription_plan_rows

revision: str = "0023_subscriptions"
down_revision: str | None = "0022_payment_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("plan_key", sa.String(length=32), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("price_kzt", sa.Integer(), nullable=True),
        sa.Column("credits_per_period", sa.Integer(), nullable=False),
        sa.Column("period_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("referral_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("localization", postgresql.JSONB(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("stars > 0", name="ck_subscription_plans_stars_positive"),
        sa.CheckConstraint(
            "credits_per_period > 0", name="ck_subscription_plans_credits_positive"
        ),
        sa.CheckConstraint("period_days > 0", name="ck_subscription_plans_period_days_positive"),
        sa.CheckConstraint(
            "price_kzt IS NULL OR price_kzt > 0",
            name="ck_subscription_plans_price_kzt_positive",
        ),
        sa.CheckConstraint(
            "referral_percent >= 0 AND referral_percent <= 100",
            name="ck_subscription_plans_referral_percent_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscription_plans"),
        sa.UniqueConstraint("slug", name="uq_subscription_plans_slug"),
        sa.UniqueConstraint("plan_key", name="uq_subscription_plans_plan_key"),
    )
    op.create_index(
        "ix_subscription_plans_display_order", "subscription_plans", ["display_order"]
    )

    op.create_table(
        "user_subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "cancel_at_period_end", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_payment_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active','cancelling','expired')",
            name="ck_user_subscriptions_status_known",
        ),
        sa.CheckConstraint(
            "current_period_end > current_period_start",
            name="ck_user_subscriptions_period_ordered",
        ),
        sa.CheckConstraint(
            "current_period_index >= 0",
            name="ck_user_subscriptions_period_index_non_negative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_payment_order_id"], ["payment_orders.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_subscriptions"),
        sa.UniqueConstraint("user_id", name="uq_user_subscriptions_user"),
    )
    op.create_index("ix_user_subscriptions_plan_id", "user_subscriptions", ["plan_id"])
    op.create_index(
        "ix_user_subscriptions_due",
        "user_subscriptions",
        ["current_period_end"],
        postgresql_where=sa.text("status IN ('active','cancelling')"),
    )

    op.create_table(
        "subscription_grants",
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_index", sa.Integer(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ledger_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("credits > 0", name="ck_subscription_grants_credits_positive"),
        sa.CheckConstraint(
            "period_index >= 0", name="ck_subscription_grants_period_index_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["user_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"], ["credit_transactions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscription_grants"),
        sa.UniqueConstraint(
            "subscription_id", "period_index", name="uq_subscription_grants_period"
        ),
        sa.UniqueConstraint(
            "ledger_transaction_id", name="uq_subscription_grants_ledger_transaction_id"
        ),
    )
    op.create_index(
        "ix_subscription_grants_subscription", "subscription_grants", ["subscription_id"]
    )

    plans = sa.table(
        "subscription_plans",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String()),
        sa.column("plan_key", sa.String()),
        sa.column("stars", sa.Integer()),
        sa.column("price_kzt", sa.Integer()),
        sa.column("credits_per_period", sa.Integer()),
        sa.column("period_days", sa.Integer()),
        sa.column("referral_percent", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("display_order", sa.Integer()),
        sa.column("localization", postgresql.JSONB()),
    )
    # Plans are seeded enabled, but the `subscriptions` feature flag below keeps every
    # surface closed until checkout is wired up and finance has signed off.
    statement = postgresql.insert(plans).values(subscription_plan_rows())
    op.get_bind().execute(
        statement.on_conflict_do_update(
            index_elements=[plans.c.slug],
            set_={
                "plan_key": statement.excluded.plan_key,
                "stars": statement.excluded.stars,
                "price_kzt": statement.excluded.price_kzt,
                "credits_per_period": statement.excluded.credits_per_period,
                "period_days": statement.excluded.period_days,
                "referral_percent": statement.excluded.referral_percent,
                "enabled": statement.excluded.enabled,
                "display_order": statement.excluded.display_order,
                "localization": statement.excluded.localization,
            },
        )
    )

    flags = sa.table(
        "feature_flags",
        sa.column("key", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("payload", postgresql.JSONB()),
    )
    flag_statement = postgresql.insert(flags).values(
        [{"key": "subscriptions", "enabled": False, "payload": {}}]
    )
    op.get_bind().execute(
        flag_statement.on_conflict_do_update(
            index_elements=[flags.c.key],
            set_={"enabled": False, "payload": flag_statement.excluded.payload},
        )
    )


def downgrade() -> None:
    # Users on a paid tier would otherwise keep a plan value with no plan row behind
    # it. Reset them to free before the tables disappear.
    op.execute(
        sa.text(
            "UPDATE users SET plan = 'free' WHERE plan IN "
            "('start','pro','studio','business')"
        )
    )
    op.execute(sa.text("DELETE FROM feature_flags WHERE key = 'subscriptions'"))
    op.drop_table("subscription_grants")
    op.drop_table("user_subscriptions")
    op.drop_table("subscription_plans")
