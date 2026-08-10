from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TelegramUpdateInbox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Minimal durable copy of a money-moving Telegram update."""

    __tablename__ = "telegram_update_inbox"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('successful_payment','subscription_state')",
            name="event_type_known",
        ),
        CheckConstraint(
            "status IN ('processing','processed','failed')",
            name="status_known",
        ),
        CheckConstraint("attempt_count >= 1", name="attempt_count_positive"),
        Index(
            "ix_telegram_update_inbox_due",
            "next_attempt_at",
            postgresql_where=text("status = 'failed'"),
        ),
    )

    update_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
