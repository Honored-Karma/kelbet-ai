"""Add the Veo route that takes reference images and first/last frames.

Revision ID: 0025_veo_consistency_video
Revises: 0024_telegram_native_subs
Create Date: 2026-08-03 21:40:00.000000

Seeds one new catalog row and its feature flag, both disabled to users: the flag
ships off because the reference-image payload is documented but has never been
sent to the live API from here.

The row is a separate SKU rather than a capability bolted onto the extended Veo
route. An extending request carries `video`, and Google excludes `image`,
`lastFrame` and `referenceImages` whenever it does, so the two cannot be the same
product without the inputs silently becoming invalid part-way through a chain.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import catalog_model_rows

revision: str = "0025_veo_consistency_video"
down_revision: str | None = "0024_telegram_native_subs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSISTENT_SLUG = "google-veo31-fast-consistent-video"
CONSISTENCY_FLAG = "veo_consistency"


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
    rows = [row for row in catalog_model_rows() if row["slug"] == CONSISTENT_SLUG]
    if rows:
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
        [{"key": CONSISTENCY_FLAG, "enabled": False, "payload": {}}]
    )
    # Only insert. Re-running must not switch the flag back off for an operator
    # who has already turned it on.
    op.get_bind().execute(flag_statement.on_conflict_do_nothing(index_elements=[flags.c.key]))


def downgrade() -> None:
    catalog = _catalog_table()
    op.get_bind().execute(sa.delete(catalog).where(catalog.c.slug == CONSISTENT_SLUG))
    flags = _flag_table()
    op.get_bind().execute(sa.delete(flags).where(flags.c.key == CONSISTENCY_FLAG))
