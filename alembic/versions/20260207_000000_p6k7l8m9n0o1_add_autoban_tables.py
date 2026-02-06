"""Add autoban_rules and autoban_logs tables.

Revision ID: p6k7l8m9n0o1
Revises: o5j6k7l8m9n0
Create Date: 2026-02-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p6k7l8m9n0o1"
down_revision: str | None = "o5j6k7l8m9n0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "autoban_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("action", sa.String(), nullable=False, server_default="ban"),
        sa.Column("pattern", sa.String(), nullable=True),
        sa.Column("use_wildcard", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("threshold_hours", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_autoban_rules_guild_id"),
        "autoban_rules",
        ["guild_id"],
        unique=False,
    )

    op.create_table(
        "autoban_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey("autoban_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_taken", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_autoban_logs_guild_id"),
        "autoban_logs",
        ["guild_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_autoban_logs_guild_id"), table_name="autoban_logs")
    op.drop_table("autoban_logs")
    op.drop_index(op.f("ix_autoban_rules_guild_id"), table_name="autoban_rules")
    op.drop_table("autoban_rules")
