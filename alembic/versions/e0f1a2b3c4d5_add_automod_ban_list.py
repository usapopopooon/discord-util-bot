"""add automod_ban_list table

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-03-22 00:00:02.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automod_ban_list",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.String(), nullable=False, index=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "guild_id", "user_id", name="uq_automod_ban_list_guild_user"
        ),
    )


def downgrade() -> None:
    op.drop_table("automod_ban_list")
