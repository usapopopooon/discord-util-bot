"""EventLog cog helper functions for embed building."""

from __future__ import annotations

from datetime import UTC, datetime

import discord

# イベントタイプごとの Embed カラー
_COLORS: dict[str, int] = {
    "message_delete": 0xE74C3C,
    "message_edit": 0xE67E22,
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
    "voice_state": 0x3498DB,
}


def create_event_embed(title: str, event_type: str) -> discord.Embed:
    """Create a timestamped embed with the event type's color."""
    return discord.Embed(
        title=title,
        color=_COLORS[event_type],
        timestamp=datetime.now(UTC),
    )


def add_user_field(
    embed: discord.Embed,
    user: discord.User | discord.Member,
    *,
    label: str = "User",
) -> None:
    """Add a user mention field: <@id> (username)."""
    embed.add_field(name=label, value=f"<@{user.id}> ({user.name})", inline=True)


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


async def find_audit_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: int,
    *,
    limit: int = 5,
    window_seconds: float = 5,
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
