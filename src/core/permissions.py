"""Pure functions for permission calculations."""

import discord


def build_locked_overwrites(
    guild: discord.Guild,
    owner_id: int,
    allowed_user_ids: list[int] | None = None,
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    """Build permission overwrites for a locked channel.

    Args:
        guild: The Discord guild
        owner_id: The channel owner's user ID
        allowed_user_ids: List of user IDs allowed to join

    Returns:
        Dictionary of permission overwrites
    """
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(connect=False),
    }

    # Owner always has full access
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

    # Add allowed users
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
    """Build permission overwrites for an unlocked channel.

    Args:
        guild: The Discord guild
        owner_id: The channel owner's user ID
        blocked_user_ids: List of user IDs blocked from joining

    Returns:
        Dictionary of permission overwrites
    """
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}

    # Owner has moderation permissions
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

    # Add blocked users
    if blocked_user_ids:
        for user_id in blocked_user_ids:
            member = guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(connect=False)

    return overwrites


def is_owner(session_owner_id: str, user_id: int) -> bool:
    """Check if a user is the session owner.

    Args:
        session_owner_id: The owner ID stored in the session
        user_id: The user ID to check

    Returns:
        True if the user is the owner
    """
    return session_owner_id == str(user_id)
