"""Add auto_reaction_configs table.

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2026-05-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i4d5e6f7g8h9"
down_revision: str | None = "h3c4d5e6f7g8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auto_reaction_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.String(), nullable=False, index=True),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("emojis", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "guild_id", "channel_id", name="uq_auto_reaction_guild_channel"
        ),
    )


def downgrade() -> None:
    op.drop_table("auto_reaction_configs")
