"""EventLog cog helper functions for embed building."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import discord

_JST = timezone(timedelta(hours=9))

# イベントタイプごとの Embed カラー
_COLORS: dict[str, int] = {
    "message_delete": 0xE74C3C,
    "message_edit": 0xE67E22,
    "message_purge": 0xE74C3C,
    "member_join": 0x2ECC71,
    "member_leave": 0xE74C3C,
    "member_kick": 0xE67E22,
    "member_ban": 0xE74C3C,
    "member_unban": 0x2ECC71,
    "member_timeout": 0xF1C40F,
    "role_change": 0xE67E22,
    "nickname_change": 0x3498DB,
    "channel_create": 0x2ECC71,
    "channel_delete": 0xE74C3C,
    "channel_update": 0xE67E22,
    "role_create": 0x2ECC71,
    "role_delete": 0xE74C3C,
    "role_update": 0xE67E22,
    "voice_state": 0x3498DB,
    "invite_create": 0x2ECC71,
    "invite_delete": 0xE74C3C,
    "thread_create": 0x2ECC71,
    "thread_delete": 0xE74C3C,
    "thread_update": 0xE67E22,
    "server_update": 0xE67E22,
    "emoji_update": 0xE67E22,
}


def create_event_embed(title: str, event_type: str) -> discord.Embed:
    """Create a timestamped embed with the event type's color."""
    now = datetime.now(UTC)
    embed = discord.Embed(
        title=title,
        color=_COLORS[event_type],
        timestamp=now,
    )
    embed.set_footer(text=f"記録時刻: {now.astimezone(_JST):%Y-%m-%d %H:%M:%S} JST")
    return embed


def add_user_field(
    embed: discord.Embed,
    user: discord.User | discord.Member,
    *,
    label: str = "User",
) -> None:
    """Add a user mention, name snapshot and immutable ID field."""
    embed.add_field(
        name=label,
        value=f"<@{user.id}> ({user.name})\nID: `{user.id}`",
        inline=True,
    )


def set_user_thumbnail(
    embed: discord.Embed,
    user: discord.User | discord.Member,
) -> None:
    """Set embed thumbnail to user's avatar if available."""
    if user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)


def truncate_content(content: str, max_len: int = 1024) -> str:
    """Truncate content with ellipsis if it exceeds max_len."""
    if len(content) > max_len:
        return content[: max_len - 3] + "..."
    return content


def format_datetime_with_relative(
    dt: datetime | None, fallback: str = "Unknown"
) -> str:
    """Format a datetime in JST and include Discord's relative timestamp."""
    if dt is None:
        return fallback
    unix = int(dt.timestamp())
    return f"{dt.astimezone(_JST):%Y-%m-%d %H:%M:%S} JST (<t:{unix}:R>)"


def format_permission_changes(
    before: discord.Permissions,
    after: discord.Permissions,
) -> list[str]:
    """Return concrete permission additions and removals."""
    added = sorted(name for name, value in after if value and not getattr(before, name))
    removed = sorted(
        name for name, value in before if value and not getattr(after, name)
    )
    lines: list[str] = []
    if added:
        lines.append("+ " + ", ".join(name.replace("_", " ").title() for name in added))
    if removed:
        lines.append(
            "- " + ", ".join(name.replace("_", " ").title() for name in removed)
        )
    return lines


async def find_audit_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: int,
    *,
    limit: int = 8,
    window_seconds: float = 10,
) -> tuple[int | None, str | None]:
    """Search audit log for a matching entry within the time window.

    Returns (moderator_user_id, reason) or (None, None).
    Silently returns (None, None) on Forbidden/HTTPException.
    """
    try:
        async for entry in guild.audit_logs(limit=limit, action=action):
            if (
                entry.target
                and entry.target.id == target_id
                and entry.created_at
                and (datetime.now(UTC) - entry.created_at).total_seconds()
                < window_seconds
            ):
                mod_id = entry.user.id if entry.user else None
                return mod_id, entry.reason
    except (discord.Forbidden, discord.HTTPException):
        pass
    return None, None
