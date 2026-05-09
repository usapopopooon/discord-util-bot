"""Domain-agnostic shared building blocks.

This package intentionally contains only reusable, non-domain-specific logic.
Feature-specific business rules must remain in feature modules.
"""

from src.shared.builders import (
    DEFAULT_CHANNEL_TEMPLATE,
    build_channel_name,
    build_user_limit_options,
    truncate_name,
)
from src.shared.concurrency import (
    clear_resource_locks,
    get_resource_lock,
    get_resource_lock_count,
)
from src.shared.permissions import (
    build_locked_overwrites,
    build_unlocked_overwrites,
    is_owner,
)
from src.shared.validators import (
    MAX_CHANNEL_NAME_LENGTH,
    MAX_USER_LIMIT,
    MIN_CHANNEL_NAME_LENGTH,
    MIN_USER_LIMIT,
    validate_bitrate,
    validate_channel_name,
    validate_user_limit,
)

__all__ = [
    "DEFAULT_CHANNEL_TEMPLATE",
    "MAX_CHANNEL_NAME_LENGTH",
    "MAX_USER_LIMIT",
    "MIN_CHANNEL_NAME_LENGTH",
    "MIN_USER_LIMIT",
    "build_channel_name",
    "build_locked_overwrites",
    "build_unlocked_overwrites",
    "build_user_limit_options",
    "clear_resource_locks",
    "get_resource_lock",
    "get_resource_lock_count",
    "is_owner",
    "truncate_name",
    "validate_bitrate",
    "validate_channel_name",
    "validate_user_limit",
]
