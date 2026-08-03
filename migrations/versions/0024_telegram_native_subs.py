"""Make subscriptions billable by Telegram rather than renewed on a local clock.

Revision ID: 0024_telegram_native_subs
Revises: 0023_subscriptions
Create Date: 2026-08-03 19:15:00.000000

0023 shipped the ledger side: plans, one subscription per user, and grants guarded by
UNIQUE(subscription_id, period_index). What it could not do was collect money. Renewal was
driven by `current_period_end = start + period_days` and `process_due` credited the next
period on that schedule, so a subscriber would have received credits every 30 days for a
single payment. The flag was off and nothing called the service, so nothing shipped broken —
but the hole had to be closed before it ever could.

Telegram bills recurring Stars subscriptions itself. It keeps the clock, charges the card,
and delivers each payment as a `successful_payment` carrying the **original**
`invoice_payload` with a **new** `telegram_payment_charge_id`. This migration adds the
identity needed to receive those payments:

- `user_subscriptions.invoice_payload` — the payload Telegram echoes on every renewal.
- `user_subscriptions.root_charge_id` — the first charge, which `editUserStarSubscription`
  requires in order to stop renewal.
- `subscription_grants.charge_id` — which charge paid for a period, and a third guard
  against double-crediting. `period_index` defends against a replayed renewal;
  `charge_id` defends against a redelivered update, which is what Telegram actually
  produces.

All three are nullable and additive, so rows created by 0023 remain valid, and a period
granted outside Telegram (an operator comp) simply has no charge id.

The status CHECK is widened for two states the billing flow needs: `pending` for a
subscription whose invoice link exists but which Telegram has not charged yet, and
`payment_failed` for a renewal Telegram could not collect. Neither revokes access — the
paid period still runs to `current_period_end`, which is what Telegram guarantees.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_telegram_native_subs"
down_revision: str | None = "0023_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_STATUSES = "status IN ('active','cancelling','expired')"
_NEW_STATUSES = "status IN ('pending','active','cancelling','payment_failed','expired')"


def upgrade() -> None:
    op.add_column(
        "user_subscriptions",
        sa.Column("invoice_payload", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "user_subscriptions",
        sa.Column("root_charge_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "user_subscriptions",
        sa.Column("renewal_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Unique so a payload or a charge id can identify exactly one subscription. Postgres
    # allows any number of NULLs in a unique index, so rows without them are unaffected.
    op.create_unique_constraint(
        "uq_user_subscriptions_invoice_payload", "user_subscriptions", ["invoice_payload"]
    )
    op.create_unique_constraint(
        "uq_user_subscriptions_root_charge_id", "user_subscriptions", ["root_charge_id"]
    )

    op.add_column(
        "subscription_grants",
        sa.Column("charge_id", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_subscription_grants_charge_id", "subscription_grants", ["charge_id"]
    )

    op.drop_constraint("ck_user_subscriptions_status_known", "user_subscriptions", type_="check")
    op.create_check_constraint(
        "ck_user_subscriptions_status_known", "user_subscriptions", _NEW_STATUSES
    )


def downgrade() -> None:
    # Any row left in one of the new states would violate the narrower constraint, so they
    # are folded onto the closest state 0023 understood: a subscription that was never
    # charged never really existed, and a failed renewal is still inside its paid period.
    op.execute("DELETE FROM user_subscriptions WHERE status = 'pending'")
    op.execute("UPDATE user_subscriptions SET status = 'active' WHERE status = 'payment_failed'")
    op.drop_constraint("ck_user_subscriptions_status_known", "user_subscriptions", type_="check")
    op.create_check_constraint(
        "ck_user_subscriptions_status_known", "user_subscriptions", _OLD_STATUSES
    )

    op.drop_constraint("uq_subscription_grants_charge_id", "subscription_grants", type_="unique")
    op.drop_column("subscription_grants", "charge_id")
    op.drop_constraint(
        "uq_user_subscriptions_root_charge_id", "user_subscriptions", type_="unique"
    )
    op.drop_constraint(
        "uq_user_subscriptions_invoice_payload", "user_subscriptions", type_="unique"
    )
    op.drop_column("user_subscriptions", "renewal_failed_at")
    op.drop_column("user_subscriptions", "root_charge_id")
    op.drop_column("user_subscriptions", "invoice_payload")
