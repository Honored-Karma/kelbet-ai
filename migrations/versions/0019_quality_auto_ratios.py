"""Add provider-supported automatic composition choices to Quality image models.

Revision ID: 0019_quality_auto_ratios
Revises: 0018_openai_image_provider
Create Date: 2026-08-02 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import catalog_model_rows

revision: str = "0019_quality_auto_ratios"
down_revision: str | None = "0018_openai_image_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUALITY_MODEL_SLUGS = {
    "runway-seedream5-pro-image",
    "runway-seedream5-pro-edit",
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
    catalog = _catalog_table()
    rows = [row for row in catalog_model_rows() if row["slug"] in QUALITY_MODEL_SLUGS]
    statement = postgresql.insert(catalog).values(rows)
    mutable_columns = {
        column.name: getattr(statement.excluded, column.name)
        for column in catalog.c
        if column.name not in {"id", "slug"}
    }
    op.get_bind().execute(
        statement.on_conflict_do_update(index_elements=[catalog.c.slug], set_=mutable_columns)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE catalog_models
            SET
                capabilities = jsonb_set(
                    capabilities,
                    '{resolutions}',
                    '["1k", "2k"]'::jsonb,
                    true
                ),
                pricing_rules = jsonb_set(
                    pricing_rules,
                    '{resolution_multipliers}',
                    '{"1k": {"num": 1, "den": 1}, "2k": {"num": 5, "den": 3}}'::jsonb,
                    true
                )
            WHERE slug IN ('runway-seedream5-pro-image', 'runway-seedream5-pro-edit')
            """
        )
    )
