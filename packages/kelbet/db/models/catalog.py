from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from kelbet.domain.enums import Modality


class CatalogModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "catalog_models"

    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replacement_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_flag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_credit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_cost_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    input_requirements: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    localization: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    pricing_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def modality_enum(self) -> Modality:
        return Modality(self.modality)


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class PriceQuote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "price_quotes"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("catalog_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    user_credit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
