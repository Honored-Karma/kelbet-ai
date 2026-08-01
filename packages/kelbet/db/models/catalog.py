from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
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


class GenerationTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "generation_templates"
    __table_args__ = (
        CheckConstraint("version > 0", name="generation_template_version_positive"),
        CheckConstraint("kind IN ('image', 'video')", name="generation_template_kind_valid"),
        CheckConstraint(
            "duration_sec IS NULL OR duration_sec > 0",
            name="generation_template_duration_positive",
        ),
        Index(
            "ix_generation_templates_active_order",
            "kind",
            "enabled",
            "display_order",
        ),
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    localization: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prompt_preset: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    aspect_ratio: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compatible_modalities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    required_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    preview_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    compositor: Mapped[str | None] = mapped_column(String(32), nullable=True)


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
    template_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("generation_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    template_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    template_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
