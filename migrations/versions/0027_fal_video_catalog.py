"""Seed the third-party video catalog served through the single fal.ai key.

Revision ID: 0027_fal_video_catalog
Revises: 0026_telegram_update_inbox
Create Date: 2026-08-14 00:40:00.000000

Adds thirteen video SKUs (Kling 2.5/2.6/3.0/2.1 Master/O3 4K, Seedance 2.0 and its
Fast tier, Wan 2.5 and 2.7, PixVerse 4.5, Luma Ray 2 Flash, Grok Imagine, Hailuo 2.3)
and two feature flags.

Both flags ship off. fal is a paid third-party account and not one clip has been
reconciled against a live invoice yet, so opening these to users before the first
reconciliation would spend real money on unverified per-second rates. The flags are
split by price band on purpose: `fal_video` covers the nine SKUs at 38-140 credits,
`fal_video_premium` the four at 242-525, so the cheap half can open first without
exposing a single 525-credit button.

The rows themselves are `enabled` because `enabled` means "this SKU exists and is not
retired"; user visibility is the flag's job. That split already governs the Veo
extended and consistency routes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import fal_video_rows

revision: str = "0027_fal_video_catalog"
down_revision: str | None = "0026_telegram_update_inbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FAL_FLAGS = ("fal_video", "fal_video_premium")


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


def _flag_table() -> sa.TableClause:
    return sa.table(
        "feature_flags",
        sa.column("key", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("payload", postgresql.JSONB()),
    )


def upgrade() -> None:
    catalog = _catalog_table()
    rows = fal_video_rows()
    statement = postgresql.insert(catalog).values(rows)
    mutable_columns = {
        column.name: getattr(statement.excluded, column.name)
        for column in catalog.c
        if column.name not in {"id", "slug"}
    }
    op.get_bind().execute(
        statement.on_conflict_do_update(index_elements=[catalog.c.slug], set_=mutable_columns)
    )

    flags = _flag_table()
    flag_statement = postgresql.insert(flags).values(
        [{"key": key, "enabled": False, "payload": {}} for key in FAL_FLAGS]
    )
    # Insert only. Re-running must not switch a flag back off for an operator who has
    # already opened the catalog.
    op.get_bind().execute(flag_statement.on_conflict_do_nothing(index_elements=[flags.c.key]))


def downgrade() -> None:
    catalog = _catalog_table()
    slugs = [row["slug"] for row in fal_video_rows()]
    op.get_bind().execute(sa.delete(catalog).where(catalog.c.slug.in_(slugs)))
    flags = _flag_table()
    op.get_bind().execute(sa.delete(flags).where(flags.c.key.in_(FAL_FLAGS)))
