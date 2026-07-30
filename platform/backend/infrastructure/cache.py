"""In-memory TTL cache. Same style as api/rate_limit.py (dict + timestamp,
lazy expiration) — no Redis, a deliberate project architecture decision.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Any

_MISSING = object()


class TTLCache:
    """Time-expiring cache. No background cleanup thread: expired entries
    are lazily dropped in `get()`."""

    def __init__(self, ttl_seconds: float, *, now_fn: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._now = now_fn
        self._store: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Any:
        entry = self._store.get(key, _MISSING)
        if entry is _MISSING:
            return _MISSING
        expires_at, value = entry
        if self._now() >= expires_at:
            self._store.pop(key, None)
            return _MISSING
        return value

    def set(self, key: Hashable, value: Any) -> None:
        self._store[key] = (self._now() + self._ttl, value)

    def invalidate_prefix(self, prefix: Hashable) -> None:
        """Deletes every tuple key whose first element is `prefix`. Used by
        `save_turn` to invalidate a session's cached history as soon as a
        new turn is saved."""
        stale = [k for k in self._store if isinstance(k, tuple) and k and k[0] == prefix]
        for k in stale:
            self._store.pop(k, None)
