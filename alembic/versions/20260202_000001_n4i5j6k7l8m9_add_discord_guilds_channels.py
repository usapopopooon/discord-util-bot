"""Add discord_guilds and discord_channels tables.

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-02-02 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n4i5j6k7l8m9"
down_revision: str | None = "m3h4i5j6k7l8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # discord_guilds テーブル作成
    # Bot が参加しているサーバーの情報をキャッシュ
    op.create_table(
        "discord_guilds",
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("guild_name", sa.String(), nullable=False),
        sa.Column("icon_hash", sa.String(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("guild_id"),
    )

    # discord_channels テーブル作成
    # Bot が参加しているサーバーのチャンネル情報をキャッシュ
    op.create_table(
        "discord_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("channel_name", sa.String(), nullable=False),
        sa.Column("channel_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "channel_id", name="uq_guild_channel"),
    )
    op.create_index(
        op.f("ix_discord_channels_guild_id"),
        "discord_channels",
        ["guild_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discord_channels_channel_id"),
        "discord_channels",
        ["channel_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_discord_channels_channel_id"), table_name="discord_channels")
    op.drop_index(op.f("ix_discord_channels_guild_id"), table_name="discord_channels")
    op.drop_table("discord_channels")
    op.drop_table("discord_guilds")
