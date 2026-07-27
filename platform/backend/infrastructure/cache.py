"""Caché TTL in-memory. Mismo estilo que api/rate_limit.py (dict + timestamp,
expiración perezosa) — sin Redis, decisión de arquitectura del proyecto.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Any

_MISSING = object()


class TTLCache:
    """Caché con expiración por tiempo. No hay hilo de limpieza en background:
    las entradas vencidas se descartan perezosamente en `get()`."""

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
        """Borra todas las claves tuple cuyo primer elemento sea `prefix`.
        Usado por `save_turn` para invalidar el historial cacheado de una
        sesión en cuanto se guarda un turno nuevo."""
        stale = [k for k in self._store if isinstance(k, tuple) and k and k[0] == prefix]
        for k in stale:
            self._store.pop(k, None)
