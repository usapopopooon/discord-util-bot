"""Tests for shared/common compatibility shims."""

from src.shared.builders import build_channel_name
from src.shared.concurrency import (
    clear_resource_locks,
    get_resource_lock,
    get_resource_lock_count,
)
from src.shared.validators import validate_channel_name
from src.utils import (
    clear_resource_locks as clear_utils_resource_locks,
)
from src.utils import get_resource_lock as get_resource_lock_from_utils


def test_core_builder_compatibility() -> None:
    assert build_channel_name("Alice") == "Alice's Channel"


def test_core_validator_compatibility() -> None:
    assert validate_channel_name("general") is True


def test_shared_concurrency_lock_singleton_per_key() -> None:
    clear_resource_locks()
    lock1 = get_resource_lock("guild:1")
    lock2 = get_resource_lock("guild:1")
    assert lock1 is lock2
    assert get_resource_lock_count() == 1


def test_utils_lock_api_singleton_per_key() -> None:
    clear_utils_resource_locks()
    lock1 = get_resource_lock_from_utils("channel:100")
    lock2 = get_resource_lock_from_utils("channel:100")
    assert lock1 is lock2
