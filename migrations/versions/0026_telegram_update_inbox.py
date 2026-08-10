"""Add a durable inbox for money-moving Telegram updates.

Revision ID: 0026_telegram_update_inbox
Revises: 0025_veo_consistency_video
Create Date: 2026-08-10 12:00:00.000000

Only normalized payment/subscription fields are stored. The row deliberately excludes
message text, names, usernames, shipping data and Telegram's raw update document.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_telegram_update_inbox"
down_revision: str | None = "0025_veo_consistency_video"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_update_inbox",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "attempt_count >= 1",
            name="ck_telegram_update_inbox_attempt_count_positive",
        ),
        sa.CheckConstraint(
            "event_type IN ('successful_payment','subscription_state')",
            name="ck_telegram_update_inbox_event_type_known",
        ),
        sa.CheckConstraint(
            "status IN ('processing','processed','failed')",
            name="ck_telegram_update_inbox_status_known",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_telegram_update_inbox"),
        sa.UniqueConstraint("update_id", name="uq_telegram_update_inbox_update_id"),
    )
    op.create_index(
        "ix_telegram_update_inbox_due",
        "telegram_update_inbox",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("status = 'failed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_update_inbox_due", table_name="telegram_update_inbox")
    op.drop_table("telegram_update_inbox")
