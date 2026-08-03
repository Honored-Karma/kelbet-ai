from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from kelbet.db.models.user import User


class SubscriptionPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Priced tier. Seeded by migration, editable by operators afterwards."""

    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("stars > 0", name="stars_positive"),
        CheckConstraint("credits_per_period > 0", name="credits_positive"),
        CheckConstraint("period_days > 0", name="period_days_positive"),
        CheckConstraint("price_kzt IS NULL OR price_kzt > 0", name="price_kzt_positive"),
        CheckConstraint(
            "referral_percent >= 0 AND referral_percent <= 100",
            name="referral_percent_range",
        ),
    )

    slug: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    #: Value written to users.plan; must match a kelbet.domain.enums.Plan member.
    plan_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Card price for the web channel. NULL while that channel is not live.
    price_kzt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits_per_period: Mapped[int] = mapped_column(Integer, nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    referral_percent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    localization: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    subscriptions: Mapped[list[UserSubscription]] = relationship(
        "UserSubscription",
        back_populates="plan",
        lazy="selectin",
    )


class UserSubscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """At most one subscription per user. Period bounds drive the grant schedule."""

    __tablename__ = "user_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_subscriptions_user"),
        CheckConstraint("status IN ('active','cancelling','expired')", name="status_known"),
        CheckConstraint("current_period_end > current_period_start", name="period_ordered"),
        CheckConstraint("current_period_index >= 0", name="period_index_non_negative"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Monotonic counter. Doubles as the idempotency discriminator for grants, so a
    #: replayed renewal can never hand out a second period of credits.
    current_period_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: One-tap cancel: the user keeps the paid period and simply stops renewing. No
    #: support ticket, which is the loudest complaint about competing services.
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_payment_order_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    plan: Mapped[SubscriptionPlan] = relationship(
        "SubscriptionPlan",
        back_populates="subscriptions",
        lazy="selectin",
    )
    grants: Mapped[list[SubscriptionGrant]] = relationship(
        "SubscriptionGrant",
        back_populates="subscription",
        lazy="selectin",
    )


class SubscriptionGrant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per period actually credited. The uniqueness is the safety property.

    UNIQUE(subscription_id, period_index) is what makes a duplicate renewal
    impossible at the storage layer, independently of any service-level check.
    """

    __tablename__ = "subscription_grants"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "period_index",
            name="uq_subscription_grants_period",
        ),
        CheckConstraint("credits > 0", name="credits_positive"),
        CheckConstraint("period_index >= 0", name="period_index_non_negative"),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_index: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ledger_transaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=True,
    )

    subscription: Mapped[UserSubscription] = relationship(
        "UserSubscription",
        back_populates="grants",
    )
