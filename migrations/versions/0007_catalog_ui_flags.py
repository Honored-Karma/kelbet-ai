"""Add UI selection metadata to image catalog models.

Revision ID: 0007_catalog_ui_flags
Revises: 0006_generations
Create Date: 2026-07-30 17:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_catalog_ui_flags"
down_revision: str | None = "0006_generations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE catalog_models
            SET capabilities = jsonb_set(
                capabilities,
                '{ui}',
                '{"simple_default": false, "hidden_in_production": true}'::jsonb,
                true
            )
            WHERE slug = 'mock-image'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE catalog_models
            SET capabilities = jsonb_set(
                capabilities,
                '{ui}',
                '{"simple_default": true, "hidden_in_production": false}'::jsonb,
                true
            )
            WHERE slug = 'runway-gen4-image'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE catalog_models
            SET capabilities = capabilities - 'ui'
            WHERE slug IN ('mock-image', 'runway-gen4-image')
            """
        )
    )
