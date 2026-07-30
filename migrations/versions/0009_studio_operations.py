"""Add image operations, production presets, and asset dimensions.

Revision ID: 0009_studio_operations
Revises: 0008_assistant_notifications
Create Date: 2026-07-30 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import catalog_model_rows

revision: str = "0009_studio_operations"
down_revision: str | None = "0008_assistant_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_SLUGS = {
    "runway-seedream5-lite-image",
    "runway-seedream5-pro-image",
    "runway-seedream5-lite-edit",
    "runway-seedream5-pro-edit",
    "runway-magnific-image-upscale",
}


def _catalog_table() -> sa.TableClause:
    return sa.table(
        "catalog_models",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String()),
        sa.column("modality", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("provider_model_id", sa.String()),
        sa.column("display_order", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("deprecated_at", sa.DateTime(timezone=True)),
        sa.column("replacement_slug", sa.String()),
        sa.column("feature_flag", sa.String()),
        sa.column("user_credit_price", sa.Integer()),
        sa.column("provider_cost_units", sa.Integer()),
        sa.column("currency_hint", sa.String()),
        sa.column("capabilities", postgresql.JSONB()),
        sa.column("input_requirements", postgresql.JSONB()),
        sa.column("localization", postgresql.JSONB()),
        sa.column("pricing_rules", postgresql.JSONB()),
    )


def upgrade() -> None:
    op.add_column("generation_assets", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("generation_assets", sa.Column("height", sa.Integer(), nullable=True))

    catalog = _catalog_table()
    rows = [
        row
        for row in catalog_model_rows()
        if row["slug"] in NEW_SLUGS or row["slug"] == "runway-gen4-image"
    ]
    statement = postgresql.insert(catalog).values(rows)
    mutable_columns = {
        column.name: getattr(statement.excluded, column.name)
        for column in catalog.c
        if column.name not in {"id", "slug"}
    }
    op.get_bind().execute(
        statement.on_conflict_do_update(
            index_elements=[catalog.c.slug],
            set_=mutable_columns,
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE feature_flags
            SET enabled = false, updated_at = now()
            WHERE key = 'experimental_upscale'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM catalog_models
            WHERE slug IN (
                'runway-seedream5-lite-image',
                'runway-seedream5-pro-image',
                'runway-seedream5-lite-edit',
                'runway-seedream5-pro-edit',
                'runway-magnific-image-upscale'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE catalog_models
            SET capabilities = jsonb_set(
                capabilities,
                '{ui}',
                '{"simple_default": true, "hidden_in_production": false}'::jsonb,
                true
            )
            WHERE slug = 'runway-gen4-image'
            """
        )
    )
    op.drop_column("generation_assets", "height")
    op.drop_column("generation_assets", "width")
