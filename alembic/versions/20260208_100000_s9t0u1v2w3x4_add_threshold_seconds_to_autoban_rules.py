"""Add threshold_seconds to autoban_rules.

Revision ID: s9t0u1v2w3x4
Revises: r8m9n0o1p2q3
Create Date: 2026-02-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s9t0u1v2w3x4"
down_revision: str | None = "r8m9n0o1p2q3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "autoban_rules",
        sa.Column("threshold_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("autoban_rules", "threshold_seconds")
