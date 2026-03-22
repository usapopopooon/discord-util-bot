"""add intro_check_messages to automod_configs

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-03-22 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "automod_configs",
        sa.Column(
            "intro_check_messages",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
    )


def downgrade() -> None:
    op.drop_column("automod_configs", "intro_check_messages")
