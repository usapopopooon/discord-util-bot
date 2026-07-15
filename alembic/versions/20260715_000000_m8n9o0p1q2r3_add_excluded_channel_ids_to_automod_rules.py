"""Add excluded_channel_ids column to automod_rules.

Revision ID: m8n9o0p1q2r3
Revises: l7g8h9i0j1k2
Create Date: 2026-07-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m8n9o0p1q2r3"
down_revision: str | None = "l7g8h9i0j1k2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "automod_rules",
        sa.Column("excluded_channel_ids", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("automod_rules", "excluded_channel_ids")
