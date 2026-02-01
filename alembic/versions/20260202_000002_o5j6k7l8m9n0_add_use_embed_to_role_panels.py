"""Add use_embed column to role_panels.

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Create Date: 2026-02-02 00:00:02.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o5j6k7l8m9n0"
down_revision: str | None = "n4i5j6k7l8m9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # use_embed カラムを追加
    # デフォルト True (Embed 形式) で既存レコードも Embed 形式になる
    op.add_column(
        "role_panels",
        sa.Column("use_embed", sa.Boolean(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("role_panels", "use_embed")
