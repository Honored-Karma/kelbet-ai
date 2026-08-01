"""Add server generation templates and immutable quote/job snapshots.

Revision ID: 0014_generation_templates
Revises: 0013_moderation_consent
Create Date: 2026-08-01 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.template_seeds import template_rows

revision: str = "0014_generation_templates"
down_revision: str | None = "0013_moderation_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_templates",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("localization", postgresql.JSONB(), nullable=False),
        sa.Column("prompt_preset", postgresql.JSONB(), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("compatible_modalities", postgresql.JSONB(), nullable=False),
        sa.Column("required_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("preview_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("compositor", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("version > 0", name="generation_template_version_positive"),
        sa.CheckConstraint("kind IN ('image', 'video')", name="generation_template_kind_valid"),
        sa.CheckConstraint(
            "duration_sec IS NULL OR duration_sec > 0",
            name="generation_template_duration_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_generation_templates_slug"),
    )
    op.create_index(
        "ix_generation_templates_active_order",
        "generation_templates",
        ["kind", "enabled", "display_order"],
    )

    template_table = sa.table(
        "generation_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("version", sa.Integer),
        sa.column("kind", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("display_order", sa.Integer),
        sa.column("localization", postgresql.JSONB),
        sa.column("prompt_preset", postgresql.JSONB),
        sa.column("aspect_ratio", sa.String),
        sa.column("duration_sec", sa.Integer),
        sa.column("compatible_modalities", postgresql.JSONB),
        sa.column("required_inputs", postgresql.JSONB),
        sa.column("preview_metadata", postgresql.JSONB),
        sa.column("compositor", sa.String),
    )
    op.bulk_insert(template_table, template_rows())

    for table_name in ("price_quotes", "generation_jobs"):
        op.add_column(
            table_name,
            sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.add_column(table_name, sa.Column("template_slug", sa.String(length=64), nullable=True))
        op.add_column(table_name, sa.Column("template_version", sa.Integer(), nullable=True))
        op.add_column(
            table_name,
            sa.Column(
                "template_inputs",
                postgresql.JSONB(),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "template_snapshot",
                postgresql.JSONB(),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
        )
        op.create_foreign_key(
            f"fk_{table_name}_template_id_generation_templates",
            table_name,
            "generation_templates",
            ["template_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table_name}_template_id", table_name, ["template_id"])

    op.execute(
        """
        CREATE FUNCTION kelbet_guard_template_snapshot()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.template_id IS DISTINCT FROM OLD.template_id
               OR NEW.template_slug IS DISTINCT FROM OLD.template_slug
               OR NEW.template_version IS DISTINCT FROM OLD.template_version
               OR NEW.template_inputs IS DISTINCT FROM OLD.template_inputs
               OR NEW.template_snapshot IS DISTINCT FROM OLD.template_snapshot THEN
                RAISE EXCEPTION 'generation template snapshot is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_generation_template_snapshot_immutable
        BEFORE UPDATE ON generation_jobs
        FOR EACH ROW EXECUTE FUNCTION kelbet_guard_template_snapshot();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_quote_template_snapshot_immutable
        BEFORE UPDATE ON price_quotes
        FOR EACH ROW EXECUTE FUNCTION kelbet_guard_template_snapshot();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_quote_template_snapshot_immutable ON price_quotes")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_generation_template_snapshot_immutable ON generation_jobs"
    )
    op.execute("DROP FUNCTION IF EXISTS kelbet_guard_template_snapshot()")
    for table_name in ("generation_jobs", "price_quotes"):
        op.drop_index(f"ix_{table_name}_template_id", table_name=table_name)
        op.drop_constraint(
            f"fk_{table_name}_template_id_generation_templates",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "template_snapshot")
        op.drop_column(table_name, "template_inputs")
        op.drop_column(table_name, "template_version")
        op.drop_column(table_name, "template_slug")
        op.drop_column(table_name, "template_id")
    op.drop_index("ix_generation_templates_active_order", table_name="generation_templates")
    op.drop_table("generation_templates")
