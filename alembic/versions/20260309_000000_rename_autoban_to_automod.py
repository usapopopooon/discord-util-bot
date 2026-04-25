"""rename_autoban_to_automod

AutoBan を AutoMod にリネームし、timeout アクション用の
timeout_duration_seconds カラムを追加する。

Revision ID: a1m2o3d4r5n6
Revises: t1h2r3m4i5n6
Create Date: 2026-03-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1m2o3d4r5n6"
down_revision: str | None = "t1h2r3m4i5n6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # テーブル名を autoban → automod にリネーム
    op.rename_table("autoban_rules", "automod_rules")
    op.rename_table("autoban_configs", "automod_configs")
    op.rename_table("autoban_logs", "automod_logs")
    op.rename_table("autoban_intro_posts", "automod_intro_posts")

    # timeout アクション用のカラムを追加
    op.add_column(
        "automod_rules",
        sa.Column("timeout_duration_seconds", sa.Integer(), nullable=True),
    )

    # BanLog の is_autoban → is_automod にリネーム
    op.alter_column("ban_logs", "is_autoban", new_column_name="is_automod")


def downgrade() -> None:
    op.alter_column("ban_logs", "is_automod", new_column_name="is_autoban")

    op.drop_column("automod_rules", "timeout_duration_seconds")

    op.rename_table("automod_intro_posts", "autoban_intro_posts")
    op.rename_table("automod_logs", "autoban_logs")
    op.rename_table("automod_configs", "autoban_configs")
    op.rename_table("automod_rules", "autoban_rules")
