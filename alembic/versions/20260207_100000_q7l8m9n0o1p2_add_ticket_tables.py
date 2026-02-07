"""Add ticket_categories, ticket_panels, ticket_panel_categories, tickets tables.

Revision ID: q7l8m9n0o1p2
Revises: p6k7l8m9n0o1
Create Date: 2026-02-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q7l8m9n0o1p2"
down_revision: str | None = "p6k7l8m9n0o1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ticket_categories
    op.create_table(
        "ticket_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("staff_role_id", sa.String(), nullable=False),
        sa.Column("discord_category_id", sa.String(), nullable=True),
        sa.Column(
            "channel_prefix",
            sa.String(),
            nullable=False,
            server_default="ticket-",
        ),
        sa.Column("form_questions", sa.String(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_categories_guild_id"),
        "ticket_categories",
        ["guild_id"],
        unique=False,
    )

    # ticket_panels
    op.create_table(
        "ticket_panels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_panels_guild_id"),
        "ticket_panels",
        ["guild_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticket_panels_channel_id"),
        "ticket_panels",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticket_panels_message_id"),
        "ticket_panels",
        ["message_id"],
        unique=False,
    )

    # ticket_panel_categories (join table)
    op.create_table(
        "ticket_panel_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "panel_id",
            sa.Integer(),
            sa.ForeignKey("ticket_panels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("ticket_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("button_label", sa.String(), nullable=True),
        sa.Column(
            "button_style", sa.String(), nullable=False, server_default="primary"
        ),
        sa.Column("button_emoji", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("panel_id", "category_id", name="uq_ticket_panel_category"),
    )

    # tickets
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=True, unique=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("ticket_categories.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("closed_by", sa.String(), nullable=True),
        sa.Column("close_reason", sa.String(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("ticket_number", sa.Integer(), nullable=False),
        sa.Column("form_answers", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "ticket_number", name="uq_guild_ticket_number"),
    )
    op.create_index(
        op.f("ix_tickets_guild_id"),
        "tickets",
        ["guild_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tickets_channel_id"),
        "tickets",
        ["channel_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_tickets_user_id"),
        "tickets",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_user_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_channel_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_guild_id"), table_name="tickets")
    op.drop_table("tickets")
    op.drop_table("ticket_panel_categories")
    op.drop_index(op.f("ix_ticket_panels_message_id"), table_name="ticket_panels")
    op.drop_index(op.f("ix_ticket_panels_channel_id"), table_name="ticket_panels")
    op.drop_index(op.f("ix_ticket_panels_guild_id"), table_name="ticket_panels")
    op.drop_table("ticket_panels")
    op.drop_index(op.f("ix_ticket_categories_guild_id"), table_name="ticket_categories")
    op.drop_table("ticket_categories")
