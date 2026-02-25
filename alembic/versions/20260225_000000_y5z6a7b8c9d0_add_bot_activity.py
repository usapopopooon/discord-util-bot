"""Add bot_activity table for configurable presence.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-02-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "y5z6a7b8c9d0"
down_revision: str | None = "x4y5z6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_type",
            sa.String(),
            nullable=False,
            server_default="playing",
        ),
        sa.Column(
            "activity_text",
            sa.String(),
            nullable=False,
            server_default="お菓子を食べています",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("bot_activity")
