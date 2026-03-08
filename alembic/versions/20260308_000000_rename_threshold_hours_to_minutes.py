"""merge_threshold_hours_into_threshold_seconds

account_age ルールの閾値を threshold_hours から threshold_seconds に統合する。
既存データを時間→秒に変換し、threshold_hours カラムを削除する。

Revision ID: t1h2r3m4i5n6
Revises: h1e2a3l4t5h6
Create Date: 2026-03-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t1h2r3m4i5n6"
down_revision: Union[str, None] = "h1e2a3l4t5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # threshold_hours を秒に変換して threshold_seconds に移行
    op.execute(
        "UPDATE autoban_rules "
        "SET threshold_seconds = threshold_hours * 3600 "
        "WHERE threshold_hours IS NOT NULL"
    )
    op.drop_column("autoban_rules", "threshold_hours")


def downgrade() -> None:
    op.add_column(
        "autoban_rules",
        sa.Column("threshold_hours", sa.Integer(), nullable=True),
    )
    # account_age ルールの threshold_seconds を時間に戻す
    op.execute(
        "UPDATE autoban_rules "
        "SET threshold_hours = threshold_seconds / 3600 "
        "WHERE rule_type = 'account_age' AND threshold_seconds IS NOT NULL"
    )
    # account_age ルールの threshold_seconds をクリア
    op.execute(
        "UPDATE autoban_rules "
        "SET threshold_seconds = NULL "
        "WHERE rule_type = 'account_age'"
    )
