from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReferralCode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "referral_codes"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)


class ReferralAttribution(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "referral_attributions"
    __table_args__ = (
        UniqueConstraint("invited_user_id", name="uq_referral_attributions_invited_user"),
        CheckConstraint("inviter_user_id <> invited_user_id", name="ck_referral_no_self"),
    )

    referral_code_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("referral_codes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inviter_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invited_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attributed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReferralReward(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "referral_rewards"
    __table_args__ = (
        UniqueConstraint("attribution_id", name="uq_referral_rewards_attribution"),
        UniqueConstraint("payment_order_id", name="uq_referral_rewards_payment_order"),
        CheckConstraint("inviter_bonus_credits >= 0", name="ck_referral_inviter_bonus_nonnegative"),
        CheckConstraint("invitee_bonus_credits >= 0", name="ck_referral_invitee_bonus_nonnegative"),
    )

    attribution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("referral_attributions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payment_order_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_orders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    inviter_bonus_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    invitee_bonus_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inviter_ledger_transaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    invitee_ledger_transaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    review_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
