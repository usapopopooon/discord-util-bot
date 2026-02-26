"""add_health_configs

ギルドごとのヘルスチェック通知チャンネル設定テーブルを追加する。

Revision ID: h1e2a3l4t5h6
Revises: 38657dc9ba11
Create Date: 2026-02-26 23:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h1e2a3l4t5h6"
down_revision: Union[str, None] = "38657dc9ba11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_configs",
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("guild_id"),
    )


def downgrade() -> None:
    op.drop_table("health_configs")
