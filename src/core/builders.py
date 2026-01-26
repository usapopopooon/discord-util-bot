"""Pure functions for building strings and objects."""

# Default channel name template
DEFAULT_CHANNEL_TEMPLATE = "{name}'s Channel"


def build_channel_name(
    owner_name: str, template: str = DEFAULT_CHANNEL_TEMPLATE
) -> str:
    """Build a voice channel name from owner name and template.

    Args:
        owner_name: The display name of the channel owner
        template: The template string with {name} placeholder

    Returns:
        The formatted channel name
    """
    return template.replace("{name}", owner_name)


def build_user_limit_options() -> list[tuple[str, int]]:
    """Build options for user limit select menu.

    Returns:
        List of (label, value) tuples for the select menu
    """
    return [
        ("No Limit", 0),
        ("2 Users", 2),
        ("5 Users", 5),
        ("10 Users", 10),
        ("15 Users", 15),
        ("25 Users", 25),
        ("50 Users", 50),
    ]


def truncate_name(name: str, max_length: int = 100) -> str:
    """Truncate a name to fit Discord's channel name limit.

    Args:
        name: The name to truncate
        max_length: Maximum allowed length

    Returns:
        The truncated name
    """
    if len(name) <= max_length:
        return name
    return name[: max_length - 3] + "..."
