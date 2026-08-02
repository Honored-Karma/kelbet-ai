"""Seed opt-in OpenAI GPT Image 2 catalog routes.

Revision ID: 0018_openai_image_provider
Revises: 0017_referral_mvp
Create Date: 2026-08-02 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import catalog_model_rows, feature_flag_rows

revision: str = "0018_openai_image_provider"
down_revision: str | None = "0017_referral_mvp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPENAI_IMAGE_SLUGS = {"openai-gpt-image-2-fast", "openai-gpt-image-2-quality"}


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
    flags = sa.table(
        "feature_flags",
        sa.column("key", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("payload", postgresql.JSONB()),
    )
    flag_rows = [row for row in feature_flag_rows() if row["key"] == "openai_image"]
    flag_statement = postgresql.insert(flags).values(flag_rows)
    op.get_bind().execute(
        flag_statement.on_conflict_do_update(
            index_elements=[flags.c.key],
            set_={
                "enabled": flag_statement.excluded.enabled,
                "payload": flag_statement.excluded.payload,
            },
        )
    )

    catalog = _catalog_table()
    rows = [row for row in catalog_model_rows() if row["slug"] in OPENAI_IMAGE_SLUGS]
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
            "DELETE FROM catalog_models WHERE slug IN "
            "('openai-gpt-image-2-fast', 'openai-gpt-image-2-quality')"
        )
    )
    op.execute(sa.text("DELETE FROM feature_flags WHERE key = 'openai_image'"))
