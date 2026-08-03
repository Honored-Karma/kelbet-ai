from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SubscriptionPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A purchasable recurring tier. Seeded and editable, mirroring `payment_products`."""

    __tablename__ = "subscription_plans"
    # Mirrors the constraints on `payment_products`. A free or negative tier would produce
    # an invoice Telegram rejects, and a zero-credit tier would charge for nothing.
    __table_args__ = (
        CheckConstraint("monthly_credits > 0", name="subscription_plan_credits_positive"),
        CheckConstraint("stars > 0", name="subscription_plan_stars_positive"),
        CheckConstraint(
            "kzt_price is null or kzt_price > 0",
            name="subscription_plan_kzt_price_positive",
        ),
    )

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    monthly_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    # Card pricing for the web channel. Priced from the market at a 65% target margin
    # rather than as stars plus a markup, so it is not derivable from `stars`.
    kzt_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    localization: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One user's subscription to one tier, as Telegram sees it.

    `invoice_payload` is the identity that survives renewals: Telegram sends the original
    payload back on every recurring charge, with a new `telegram_payment_charge_id` each
    time. That is why a subscription cannot reuse `payment_orders`, whose payload is
    unique per single charge and whose processed-receipt index would reject the second
    payment as a duplicate. Per-charge facts live in `subscription_periods` instead.

    At most one non-terminal subscription per user is enforced by a partial unique index:
    a user may hold many historical rows but only one that is currently billing.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "uq_subscriptions_live_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status in ('pending', 'active', 'cancelled', 'payment_failed')"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # The price and credit grant are frozen at purchase. Repricing a plan must never
    # change what an existing subscriber already paid for.
    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    invoice_payload: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # The first charge's id. `editUserStarSubscription` addresses a subscription by this
    # id, so cancelling depends on having kept it.
    root_charge_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    terms_version: Mapped[str] = mapped_column(String(32), nullable=False)
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Telegram's own `subscription_expiration_date`, never a locally computed date. Local
    # arithmetic would drift from the clock that actually charges the user.
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SubscriptionPeriod(Base, UUIDPrimaryKeyMixin):
    """Append-only record of one paid period. One row per Telegram charge.

    The unique constraint on `charge_id` is the primary defence against granting a period's
    credits twice: Telegram redelivers updates, and the bot may process the same
    `successful_payment` more than once. The wallet ledger's idempotency key is the second,
    independent defence, so a grant has to get past both to double.
    """

    __tablename__ = "subscription_periods"
    __table_args__ = (
        CheckConstraint("credits_granted > 0", name="subscription_period_credits_positive"),
        CheckConstraint("stars_amount > 0", name="subscription_period_stars_positive"),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    charge_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    provider_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stars_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    is_first: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ledger_transaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
