"""Add chat_role_configs and chat_role_progress tables.

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-04-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h3c4d5e6f7g8"
down_revision: str | None = "g2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_role_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.String(), nullable=False, index=True),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("duration_hours", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "guild_id", "channel_id", "role_id", name="uq_chat_role_guild_ch_role"
        ),
    )

    op.create_table(
        "chat_role_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "config_id",
            sa.Integer(),
            sa.ForeignKey("chat_role_configs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.UniqueConstraint(
            "config_id", "user_id", name="uq_chat_role_progress_config_user"
        ),
    )


def downgrade() -> None:
    op.drop_table("chat_role_progress")
    op.drop_table("chat_role_configs")
