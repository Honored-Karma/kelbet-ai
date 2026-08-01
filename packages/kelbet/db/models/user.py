from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from kelbet.domain.enums import Language, Plan

if TYPE_CHECKING:
    from kelbet.db.models.auth_session import AuthSession
    from kelbet.db.models.wallet import Wallet


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default=Plan.FREE.value)
    notify_generation_ready: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    is_blocked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    wallet: Mapped[Wallet | None] = relationship(
        "Wallet",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )
    auth_sessions: Mapped[list[AuthSession]] = relationship(
        "AuthSession",
        back_populates="user",
        lazy="selectin",
    )

    def language_enum(self) -> Language:
        return Language(self.language)

    def plan_enum(self) -> Plan:
        return Plan(self.plan)
