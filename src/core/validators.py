"""Pure validation functions."""

# Discord channel name limits
MIN_CHANNEL_NAME_LENGTH = 1
MAX_CHANNEL_NAME_LENGTH = 100

# Discord voice channel user limit
MIN_USER_LIMIT = 0
MAX_USER_LIMIT = 99


def validate_user_limit(limit: int) -> bool:
    """Validate voice channel user limit.

    Args:
        limit: The user limit to validate (0 = unlimited)

    Returns:
        True if valid, False otherwise
    """
    return MIN_USER_LIMIT <= limit <= MAX_USER_LIMIT


def validate_channel_name(name: str) -> bool:
    """Validate voice channel name.

    Args:
        name: The channel name to validate

    Returns:
        True if valid, False otherwise
    """
    return MIN_CHANNEL_NAME_LENGTH <= len(name) <= MAX_CHANNEL_NAME_LENGTH


def validate_bitrate(bitrate: int) -> bool:
    """Validate voice channel bitrate.

    Args:
        bitrate: The bitrate in kbps (8-384 depending on server boost level)

    Returns:
        True if valid, False otherwise
    """
    return 8 <= bitrate <= 384
