"""Shared async concurrency primitives and helpers."""

from __future__ import annotations

import asyncio
import time

_resource_locks: dict[str, tuple[asyncio.Lock, float]] = {}
_LOCK_CLEANUP_INTERVAL = 600
_LOCK_EXPIRY_TIME = 300
_lock_last_cleanup_time = float("-inf")


def _cleanup_resource_locks() -> None:
    """Delete stale, currently-unused locks."""
    global _lock_last_cleanup_time
    now = time.monotonic()

    if (
        _lock_last_cleanup_time > 0
        and now - _lock_last_cleanup_time < _LOCK_CLEANUP_INTERVAL
    ):
        return

    _lock_last_cleanup_time = now

    for key in list(_resource_locks):
        lock, last_access = _resource_locks[key]
        if now - last_access > _LOCK_EXPIRY_TIME and not lock.locked():
            del _resource_locks[key]


def get_resource_lock(resource_key: str) -> asyncio.Lock:
    """Return a shared lock for the given resource key."""
    _cleanup_resource_locks()
    now = time.monotonic()

    entry = _resource_locks.get(resource_key)
    if entry is None:
        lock = asyncio.Lock()
        _resource_locks[resource_key] = (lock, now)
        return lock

    _resource_locks[resource_key] = (entry[0], now)
    return entry[0]


def clear_resource_locks() -> None:
    """Clear all locks (for tests)."""
    global _lock_last_cleanup_time
    _resource_locks.clear()
    _lock_last_cleanup_time = float("-inf")


def get_resource_lock_count() -> int:
    """Return current lock count (for tests/debug)."""
    return len(_resource_locks)
