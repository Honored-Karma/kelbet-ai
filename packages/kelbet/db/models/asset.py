from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kelbet.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from kelbet.domain.enums import AssetRole, AssetStatus, RetentionClass

if TYPE_CHECKING:
    from kelbet.db.models.user import User


class GenerationAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Uploaded or generated media objects."""

    __tablename__ = "generation_assets"

    # The foreign key mirrors migration 0006, which adds it additively. Declaring it here
    # is not cosmetic: without it SQLAlchemy does not know that this table depends on
    # generation_jobs, so metadata.drop_all sorts the two wrongly and Postgres refuses
    # to drop generation_jobs.
    generation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("generation_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=AssetRole.INPUT.value)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AssetStatus.PENDING.value,
    )
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    declared_byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    magic_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    retention_class: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RetentionClass.TEMP_INPUT.value,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship("User")
