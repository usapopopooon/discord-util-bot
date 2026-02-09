"""Add autoban_intro_posts table and required_channel_id column.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-02-09 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w3x4y5z6a7b8"
down_revision: str | None = "v2w3x4y5z6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # autoban_rules に required_channel_id カラム追加
    op.add_column(
        "autoban_rules",
        sa.Column("required_channel_id", sa.String(), nullable=True),
    )

    # autoban_intro_posts テーブル作成
    op.create_table(
        "autoban_intro_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.String(), nullable=False, index=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "guild_id",
            "user_id",
            "channel_id",
            name="uq_intro_guild_user_channel",
        ),
    )


def downgrade() -> None:
    op.drop_table("autoban_intro_posts")
    op.drop_column("autoban_rules", "required_channel_id")
