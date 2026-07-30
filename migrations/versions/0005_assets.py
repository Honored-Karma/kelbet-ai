"""Add generation_assets for uploads (generation FK arrives in Stage F).

Revision ID: 0005_assets
Revises: 0004_catalog
Create Date: 2026-07-30 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_assets"
down_revision: str | None = "0004_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("bucket", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("declared_byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("magic_ok", sa.Boolean(), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("retention_class", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "declared_byte_size > 0",
            name=op.f("ck_generation_assets_declared_byte_size_positive"),
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name=op.f("ck_generation_assets_byte_size_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_generation_assets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_assets")),
        sa.UniqueConstraint(
            "bucket",
            "object_key",
            name=op.f("uq_generation_assets_bucket_object_key"),
        ),
    )
    op.create_index(
        op.f("ix_generation_assets_user_id"),
        "generation_assets",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generation_assets_generation_id"),
        "generation_assets",
        ["generation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_generation_assets_generation_id"), table_name="generation_assets")
    op.drop_index(op.f("ix_generation_assets_user_id"), table_name="generation_assets")
    op.drop_table("generation_assets")
