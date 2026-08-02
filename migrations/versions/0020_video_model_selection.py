"""Expose the independent Veo route in the video model catalog.

Revision ID: 0020_video_model_selection
Revises: 0019_quality_auto_ratios
Create Date: 2026-08-02 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import catalog_model_rows

revision: str = "0020_video_model_selection"
down_revision: str | None = "0019_quality_auto_ratios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIDEO_MODEL_SLUGS = {
    "runway-gemini-omni-video-fast",
    "runway-gen45-video-quality",
    "google-veo31-lite-video-fallback",
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
    rows = [row for row in catalog_model_rows() if row["slug"] in VIDEO_MODEL_SLUGS]
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
            SET capabilities = jsonb_set(
                jsonb_set(
                    capabilities,
                    '{durations_sec}',
                    '[4, 8]'::jsonb,
                    true
                ),
                '{ui}',
                (capabilities->'ui')
                    || '{"studio_tier": "fallback", "hidden_in_production": true}'::jsonb,
                true
            ),
            pricing_rules = jsonb_set(
                pricing_rules,
                '{duration_multipliers}',
                '{"4": {"num": 1, "den": 1}, "8": {"num": 2, "den": 1}}'::jsonb,
                true
            )
            WHERE slug = 'google-veo31-lite-video-fallback'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE catalog_models
            SET capabilities = jsonb_set(capabilities, '{supports_seed}', 'true'::jsonb, true)
            WHERE slug = 'runway-gen45-video-quality'
            """
        )
    )
