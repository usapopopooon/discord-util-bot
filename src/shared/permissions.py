"""Permission overwrite calculation helpers."""

import discord


def build_locked_overwrites(
    guild: discord.Guild,
    owner_id: int,
    allowed_user_ids: list[int] | None = None,
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    """Build channel overwrites for locked mode."""
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(connect=False),
    }

    owner = guild.get_member(owner_id)
    if owner:
        overwrites[owner] = discord.PermissionOverwrite(
            connect=True,
            speak=True,
            stream=True,
            move_members=True,
            mute_members=True,
            deafen_members=True,
        )

    if allowed_user_ids:
        for user_id in allowed_user_ids:
            member = guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(connect=True)

    return overwrites


def build_unlocked_overwrites(
    guild: discord.Guild,
    owner_id: int,
    blocked_user_ids: list[int] | None = None,
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    """Build channel overwrites for unlocked mode."""
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}

    owner = guild.get_member(owner_id)
    if owner:
        overwrites[owner] = discord.PermissionOverwrite(
            connect=True,
            speak=True,
            stream=True,
            move_members=True,
            mute_members=True,
            deafen_members=True,
        )

    if blocked_user_ids:
        for user_id in blocked_user_ids:
            member = guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(connect=False)

    return overwrites


def is_owner(session_owner_id: str, user_id: int) -> bool:
    """Return whether the user is the owner of the resource."""
    return session_owner_id == str(user_id)
