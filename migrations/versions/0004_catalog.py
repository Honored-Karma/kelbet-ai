"""Catalog models, feature flags, and price quotes.

Revision ID: 0004_catalog
Revises: 0003_auth_sessions
Create Date: 2026-07-30 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import catalog_model_rows, feature_flag_rows

revision: str = "0004_catalog"
down_revision: str | None = "0003_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("modality", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_model_id", sa.String(length=128), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replacement_slug", sa.String(length=64), nullable=True),
        sa.Column("feature_flag", sa.String(length=64), nullable=True),
        sa.Column("user_credit_price", sa.Integer(), nullable=False),
        sa.Column("provider_cost_units", sa.Integer(), nullable=False),
        sa.Column("currency_hint", sa.String(length=8), nullable=True),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("localization", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pricing_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "user_credit_price > 0",
            name=op.f("ck_catalog_models_user_credit_price_positive"),
        ),
        sa.CheckConstraint(
            "provider_cost_units >= 0",
            name=op.f("ck_catalog_models_provider_cost_units_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_models")),
        sa.UniqueConstraint("slug", name=op.f("uq_catalog_models_slug")),
    )

    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.PrimaryKeyConstraint("key", name=op.f("pk_feature_flags")),
    )

    op.create_table(
        "price_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_slug", sa.String(length=64), nullable=False),
        sa.Column("user_credit_price", sa.Integer(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            "user_credit_price > 0",
            name=op.f("ck_price_quotes_user_credit_price_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_price_quotes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["catalog_models.id"],
            name=op.f("fk_price_quotes_model_id_catalog_models"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_quotes")),
    )
    op.create_index(op.f("ix_price_quotes_user_id"), "price_quotes", ["user_id"], unique=False)
    op.create_index(op.f("ix_price_quotes_model_id"), "price_quotes", ["model_id"], unique=False)
    op.create_index(
        op.f("ix_price_quotes_expires_at"),
        "price_quotes",
        ["expires_at"],
        unique=False,
    )

    catalog = sa.table(
        "catalog_models",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("modality", sa.String),
        sa.column("provider", sa.String),
        sa.column("provider_model_id", sa.String),
        sa.column("display_order", sa.Integer),
        sa.column("enabled", sa.Boolean),
        sa.column("deprecated_at", sa.DateTime(timezone=True)),
        sa.column("replacement_slug", sa.String),
        sa.column("feature_flag", sa.String),
        sa.column("user_credit_price", sa.Integer),
        sa.column("provider_cost_units", sa.Integer),
        sa.column("currency_hint", sa.String),
        sa.column("capabilities", postgresql.JSONB),
        sa.column("input_requirements", postgresql.JSONB),
        sa.column("localization", postgresql.JSONB),
        sa.column("pricing_rules", postgresql.JSONB),
    )
    flags = sa.table(
        "feature_flags",
        sa.column("key", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("payload", postgresql.JSONB),
    )

    op.bulk_insert(flags, feature_flag_rows())
    op.bulk_insert(catalog, catalog_model_rows())


def downgrade() -> None:
    op.drop_index(op.f("ix_price_quotes_expires_at"), table_name="price_quotes")
    op.drop_index(op.f("ix_price_quotes_model_id"), table_name="price_quotes")
    op.drop_index(op.f("ix_price_quotes_user_id"), table_name="price_quotes")
    op.drop_table("price_quotes")
    op.drop_table("feature_flags")
    op.drop_table("catalog_models")
