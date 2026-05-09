"""Pure validation functions for generic input constraints."""

MIN_CHANNEL_NAME_LENGTH = 1
MAX_CHANNEL_NAME_LENGTH = 100
MIN_USER_LIMIT = 0
MAX_USER_LIMIT = 99


def validate_user_limit(limit: int) -> bool:
    """Validate Discord VC user_limit range."""
    return MIN_USER_LIMIT <= limit <= MAX_USER_LIMIT


def validate_channel_name(name: str) -> bool:
    """Validate Discord channel name length."""
    return MIN_CHANNEL_NAME_LENGTH <= len(name) <= MAX_CHANNEL_NAME_LENGTH


def validate_bitrate(bitrate: int) -> bool:
    """Validate bitrate range in kbps."""
    return 8 <= bitrate <= 384
