from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from kelbet.domain.enums import Language, Plan

if TYPE_CHECKING:
    from kelbet.db.models.wallet import Wallet


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default=Plan.FREE.value)

    wallet: Mapped[Wallet | None] = relationship(
        "Wallet",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )

    def language_enum(self) -> Language:
        return Language(self.language)

    def plan_enum(self) -> Plan:
        return Plan(self.plan)
