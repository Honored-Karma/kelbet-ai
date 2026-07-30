"""Generation jobs, attempts, provider usage, webhook receipts.

Revision ID: 0006_generations
Revises: 0005_assets
Create Date: 2026-07-30 04:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_generations"
down_revision: str | None = "0005_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("modality", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_redacted", sa.Boolean(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prompt_storage_key", sa.String(length=512), nullable=True),
        sa.Column(
            "input_asset_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_credit_price", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_model_id", sa.String(length=128), nullable=False),
        sa.Column("provider_job_id", sa.String(length=128), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("progress_stage", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_class", sa.String(length=32), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_letter_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_last_event_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
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
            "progress_pct >= 0 AND progress_pct <= 100",
            name=op.f("ck_generation_jobs_progress_pct_range"),
        ),
        sa.CheckConstraint(
            "user_credit_price > 0",
            name=op.f("ck_generation_jobs_user_credit_price_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_generation_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["catalog_models.id"],
            name=op.f("fk_generation_jobs_model_id_catalog_models"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["credit_reservations.id"],
            name=op.f("fk_generation_jobs_reservation_id_credit_reservations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["price_quotes.id"],
            name=op.f("fk_generation_jobs_quote_id_price_quotes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_jobs")),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name=op.f("uq_generation_jobs_user_id_idempotency_key"),
        ),
    )
    op.create_index(
        op.f("ix_generation_jobs_user_id"),
        "generation_jobs",
        ["user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_generation_jobs_status"), "generation_jobs", ["status"], unique=False)

    op.create_table(
        "generation_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("provider_job_id", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message_safe", sa.String(length=512), nullable=True),
        sa.Column("raw_response_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["generation_jobs.id"],
            name=op.f("fk_generation_attempts_generation_id_generation_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_attempts")),
        sa.UniqueConstraint(
            "generation_id",
            "attempt_no",
            name=op.f("uq_generation_attempts_generation_id_attempt_no"),
        ),
    )
    op.create_index(
        op.f("ix_generation_attempts_generation_id"),
        "generation_attempts",
        ["generation_id"],
        unique=False,
    )

    op.create_table(
        "provider_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_model_id", sa.String(length=128), nullable=False),
        sa.Column("modality", sa.String(length=32), nullable=False),
        sa.Column("provider_cost_units", sa.Integer(), nullable=False),
        sa.Column("user_credit_price", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["generation_jobs.id"],
            name=op.f("fk_provider_usage_generation_id_generation_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["generation_attempts.id"],
            name=op.f("fk_provider_usage_attempt_id_generation_attempts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_usage")),
    )
    op.create_index(
        op.f("ix_provider_usage_generation_id"),
        "provider_usage",
        ["generation_id"],
        unique=False,
    )

    op.create_table(
        "webhook_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_receipts")),
        sa.UniqueConstraint(
            "provider",
            "event_id",
            name=op.f("uq_webhook_receipts_provider_event_id"),
        ),
    )

    # Optional FK from assets.generation_id → jobs (additive)
    op.create_foreign_key(
        op.f("fk_generation_assets_generation_id_generation_jobs"),
        "generation_assets",
        "generation_jobs",
        ["generation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_generation_assets_generation_id_generation_jobs"),
        "generation_assets",
        type_="foreignkey",
    )
    op.drop_table("webhook_receipts")
    op.drop_index(op.f("ix_provider_usage_generation_id"), table_name="provider_usage")
    op.drop_table("provider_usage")
    op.drop_index(op.f("ix_generation_attempts_generation_id"), table_name="generation_attempts")
    op.drop_table("generation_attempts")
    op.drop_index(op.f("ix_generation_jobs_status"), table_name="generation_jobs")
    op.drop_index(op.f("ix_generation_jobs_user_id"), table_name="generation_jobs")
    op.drop_table("generation_jobs")
