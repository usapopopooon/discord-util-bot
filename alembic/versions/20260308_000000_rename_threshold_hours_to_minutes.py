"""rename_threshold_hours_to_minutes

account_age ルールの閾値を時間単位から分単位に変更する。
カラム名を threshold_hours → threshold_minutes にリネームし、
既存データを 60 倍に変換する。

Revision ID: t1h2r3m4i5n6
Revises: h1e2a3l4t5h6
Create Date: 2026-03-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "t1h2r3m4i5n6"
down_revision: Union[str, None] = "h1e2a3l4t5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "autoban_rules",
        "threshold_hours",
        new_column_name="threshold_minutes",
    )
    # 既存データを時間→分に変換
    op.execute(
        "UPDATE autoban_rules SET threshold_minutes = threshold_minutes * 60 "
        "WHERE threshold_minutes IS NOT NULL"
    )


def downgrade() -> None:
    # 分→時間に変換 (端数切り捨て)
    op.execute(
        "UPDATE autoban_rules SET threshold_minutes = threshold_minutes / 60 "
        "WHERE threshold_minutes IS NOT NULL"
    )
    op.alter_column(
        "autoban_rules",
        "threshold_minutes",
        new_column_name="threshold_hours",
    )
