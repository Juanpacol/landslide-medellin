"""Tests puros de infrastructure/cache.py. Sin BD, sin red."""

from __future__ import annotations

from infrastructure.cache import _MISSING, TTLCache


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class TestTTLCache:
    def test_devuelve_missing_si_no_existe(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        assert cache.get("no-existe") is _MISSING

    def test_set_y_get(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_expira_tras_el_ttl(self) -> None:
        clock = _FakeClock()
        cache = TTLCache(ttl_seconds=10, now_fn=clock)
        cache.set("k", "v")
        clock.advance(11)
        assert cache.get("k") is _MISSING

    def test_no_expira_antes_del_ttl(self) -> None:
        clock = _FakeClock()
        cache = TTLCache(ttl_seconds=10, now_fn=clock)
        cache.set("k", "v")
        clock.advance(9)
        assert cache.get("k") == "v"

    def test_invalidate_prefix_borra_solo_las_claves_del_prefijo(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        cache.set(("session-a", 10), ["h1"])
        cache.set(("session-a", 20), ["h2"])
        cache.set(("session-b", 10), ["h3"])

        cache.invalidate_prefix("session-a")

        assert cache.get(("session-a", 10)) is _MISSING
        assert cache.get(("session-a", 20)) is _MISSING
        assert cache.get(("session-b", 10)) == ["h3"]
