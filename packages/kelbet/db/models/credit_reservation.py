from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from kelbet.domain.enums import ReservationStatus

if TYPE_CHECKING:
    from kelbet.db.models.credit_transaction import CreditTransaction
    from kelbet.db.models.user import User
    from kelbet.db.models.wallet import Wallet


class CreditReservation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "credit_reservations"

    wallet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReservationStatus.HELD.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    quote_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    capture_tx_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    refund_tx_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    held_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    wallet: Mapped[Wallet] = relationship("Wallet", back_populates="reservations")
    user: Mapped[User] = relationship("User")
    capture_tx: Mapped[CreditTransaction | None] = relationship(
        "CreditTransaction",
        foreign_keys=[capture_tx_id],
    )
    refund_tx: Mapped[CreditTransaction | None] = relationship(
        "CreditTransaction",
        foreign_keys=[refund_tx_id],
    )

    def status_enum(self) -> ReservationStatus:
        return ReservationStatus(self.status)
