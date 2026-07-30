"""Add prompt assistant requests and generation notification outbox.

Revision ID: 0008_assistant_notifications
Revises: 0007_catalog_ui_flags
Create Date: 2026-07-30 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_assistant_notifications"
down_revision: str | None = "0007_catalog_ui_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_generation_ready",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    op.create_table(
        "prompt_assistant_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("improved_prompt", sa.Text(), nullable=True),
        sa.Column("credit_cost", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_prompt_assistant_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_assistant_requests")),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_prompt_assistant_requests_user_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_prompt_assistant_requests_user_id"),
        "prompt_assistant_requests",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["generation_jobs.id"],
            name=op.f("fk_notification_outbox_generation_id_generation_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_outbox_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
        sa.UniqueConstraint(
            "channel",
            "event_type",
            "generation_id",
            name="uq_notification_outbox_generation_event",
        ),
    )
    op.create_index(
        op.f("ix_notification_outbox_generation_id"),
        "notification_outbox",
        ["generation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_outbox_user_id"),
        "notification_outbox",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_outbox_dispatch",
        "notification_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_generation_assets_history_preview",
        "generation_assets",
        ["user_id", "generation_id", "role", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generation_assets_history_preview",
        table_name="generation_assets",
    )
    op.drop_index("ix_notification_outbox_dispatch", table_name="notification_outbox")
    op.drop_index(op.f("ix_notification_outbox_user_id"), table_name="notification_outbox")
    op.drop_index(
        op.f("ix_notification_outbox_generation_id"),
        table_name="notification_outbox",
    )
    op.drop_table("notification_outbox")
    op.drop_index(
        op.f("ix_prompt_assistant_requests_user_id"),
        table_name="prompt_assistant_requests",
    )
    op.drop_table("prompt_assistant_requests")
    op.drop_column("users", "notify_generation_ready")
