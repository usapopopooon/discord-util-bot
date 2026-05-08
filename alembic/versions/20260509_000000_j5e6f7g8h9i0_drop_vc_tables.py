"""Drop VC-related tables (lobbies / voice_sessions / voice_session_members).

VC 機能は ../tmp-vc-bot に委譲したため、こちら側のテーブルは不要となった。

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2026-05-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j5e6f7g8h9i0"
down_revision: str | None = "i4d5e6f7g8h9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 子テーブルから先に削除する (FK 制約のため)
    op.drop_index(op.f("ix_voice_session_members_user_id"), "voice_session_members")
    op.drop_table("voice_session_members")

    op.drop_index(op.f("ix_voice_sessions_channel_id"), "voice_sessions")
    op.drop_table("voice_sessions")

    op.drop_index(op.f("ix_lobbies_lobby_channel_id"), "lobbies")
    op.drop_index(op.f("ix_lobbies_guild_id"), "lobbies")
    op.drop_table("lobbies")


def downgrade() -> None:
    # 親テーブルから順に再作成する
    op.create_table(
        "lobbies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("lobby_channel_id", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column(
            "default_user_limit", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lobbies_guild_id"), "lobbies", ["guild_id"], unique=False)
    op.create_index(
        op.f("ix_lobbies_lobby_channel_id"),
        "lobbies",
        ["lobby_channel_id"],
        unique=True,
    )

    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lobby_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("user_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "is_hidden", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lobby_id"], ["lobbies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_voice_sessions_channel_id"),
        "voice_sessions",
        ["channel_id"],
        unique=True,
    )

    op.create_table(
        "voice_session_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "voice_session_id",
            sa.Integer(),
            sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("voice_session_id", "user_id", name="uq_session_user"),
    )
    op.create_index(
        op.f("ix_voice_session_members_user_id"),
        "voice_session_members",
        ["user_id"],
        unique=False,
    )
