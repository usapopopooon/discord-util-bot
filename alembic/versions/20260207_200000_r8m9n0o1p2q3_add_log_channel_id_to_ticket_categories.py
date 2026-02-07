"""Add log_channel_id to ticket_categories.

Revision ID: r8m9n0o1p2q3
Revises: q7l8m9n0o1p2
Create Date: 2026-02-07 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r8m9n0o1p2q3"
down_revision: str | None = "q7l8m9n0o1p2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ticket_categories",
        sa.Column("log_channel_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ticket_categories", "log_channel_id")
