"""Add discord_roles table.

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-02-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m3h4i5j6k7l8"
down_revision: str | None = "l2g3h4i5j6k7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # discord_roles テーブル作成
    # Bot が参加しているサーバーのロール情報をキャッシュ
    op.create_table(
        "discord_roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("role_name", sa.String(), nullable=False),
        sa.Column("color", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "role_id", name="uq_guild_role"),
    )
    op.create_index(
        op.f("ix_discord_roles_guild_id"),
        "discord_roles",
        ["guild_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discord_roles_role_id"),
        "discord_roles",
        ["role_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_discord_roles_role_id"), table_name="discord_roles")
    op.drop_index(op.f("ix_discord_roles_guild_id"), table_name="discord_roles")
    op.drop_table("discord_roles")
