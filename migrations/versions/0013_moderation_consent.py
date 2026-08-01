"""Add privacy-safe moderation decisions and versioned photo consent.

Revision ID: 0013_moderation_consent
Revises: 0012_admin_operator_audit
Create Date: 2026-08-01 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_moderation_consent"
down_revision: str | None = "0012_admin_operator_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "moderation_decisions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asset_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("context", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_model", sa.String(length=128), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("review_outcome", sa.String(length=32), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("mode IN ('off', 'report', 'block')", name="moderation_mode_valid"),
        sa.CheckConstraint(
            "outcome IN ('allow', 'report', 'block')", name="moderation_outcome_valid"
        ),
        sa.CheckConstraint(
            "review_status IN ('open', 'reviewed')", name="moderation_review_status_valid"
        ),
        sa.ForeignKeyConstraint(["generation_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "context",
            "idempotency_key",
            name="uq_moderation_decisions_user_context_idempotency",
        ),
    )
    op.create_index("ix_moderation_decisions_created_at", "moderation_decisions", ["created_at"])
    op.create_index(
        "ix_moderation_decisions_generation_id", "moderation_decisions", ["generation_id"]
    )
    op.create_index("ix_moderation_decisions_outcome", "moderation_decisions", ["outcome"])
    op.create_index("ix_moderation_decisions_user_id", "moderation_decisions", ["user_id"])

    op.create_table(
        "user_consents",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("asset_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "consent_type",
            "idempotency_key",
            name="uq_user_consents_user_type_idempotency",
        ),
    )
    op.create_index("ix_user_consents_generation_id", "user_consents", ["generation_id"])
    op.create_index("ix_user_consents_user_id", "user_consents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_consents_user_id", table_name="user_consents")
    op.drop_index("ix_user_consents_generation_id", table_name="user_consents")
    op.drop_table("user_consents")
    op.drop_index("ix_moderation_decisions_user_id", table_name="moderation_decisions")
    op.drop_index("ix_moderation_decisions_outcome", table_name="moderation_decisions")
    op.drop_index("ix_moderation_decisions_generation_id", table_name="moderation_decisions")
    op.drop_index("ix_moderation_decisions_created_at", table_name="moderation_decisions")
    op.drop_table("moderation_decisions")
