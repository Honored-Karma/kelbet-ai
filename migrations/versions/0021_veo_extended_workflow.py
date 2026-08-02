"""Add durable Veo extended generation workflow.

Revision ID: 0021_veo_extended_workflow
Revises: 0020_video_model_selection
Create Date: 2026-08-02 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from kelbet.catalog.seeds import catalog_model_rows

revision: str = "0021_veo_extended_workflow"
down_revision: str | None = "0020_video_model_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_workflow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_job_id", sa.String(length=128), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cumulative_duration_sec", sa.Integer(), nullable=False),
        sa.Column("intermediate_object_key", sa.String(length=512), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="generation_workflow_attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "cumulative_duration_sec > 0",
            name="generation_workflow_duration_positive",
        ),
        sa.CheckConstraint(
            "step_index >= 0",
            name="generation_workflow_step_index_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["generation_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generation_id",
            "step_index",
            name="uq_generation_workflow_steps_generation_step",
        ),
    )
    op.create_index(
        op.f("ix_generation_workflow_steps_generation_id"),
        "generation_workflow_steps",
        ["generation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generation_workflow_steps_status"),
        "generation_workflow_steps",
        ["status"],
        unique=False,
    )

    flag_table = sa.table(
        "feature_flags",
        sa.column("key", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("payload", postgresql.JSONB()),
    )
    op.get_bind().execute(
        postgresql.insert(flag_table)
        .values(key="veo_extended", enabled=False, payload={})
        .on_conflict_do_nothing(index_elements=[flag_table.c.key])
    )

    catalog = sa.table(
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
    row = next(
        item
        for item in catalog_model_rows()
        if item["slug"] == "google-veo31-fast-extended-video"
    )
    statement = postgresql.insert(catalog).values(row)
    op.get_bind().execute(
        statement.on_conflict_do_update(
            index_elements=[catalog.c.slug],
            set_={
                column.name: getattr(statement.excluded, column.name)
                for column in catalog.c
                if column.name not in {"id", "slug"}
            },
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM catalog_models WHERE slug = 'google-veo31-fast-extended-video'")
    )
    op.execute(sa.text("DELETE FROM feature_flags WHERE key = 'veo_extended'"))
    op.drop_index(
        op.f("ix_generation_workflow_steps_status"),
        table_name="generation_workflow_steps",
    )
    op.drop_index(
        op.f("ix_generation_workflow_steps_generation_id"),
        table_name="generation_workflow_steps",
    )
    op.drop_table("generation_workflow_steps")
