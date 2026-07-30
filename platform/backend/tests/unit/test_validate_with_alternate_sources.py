"""Tests for evaluation/validate_with_alternate_sources.py's pure logic — no DB, no network.
The script's `collect_results()` needs a real Supabase connection and live SRTM access, and is
exercised by hand (see docs/research/alternate_sources_validation_2026-07-30.md); this covers the
one piece that's fully pure: deciding which communes' historical rain is recent enough to use.
"""

from __future__ import annotations

from datetime import date

from evaluation.validate_with_alternate_sources import MAX_STALENESS_DAYS, _usable_communes


def test_recent_commune_is_usable():
    today = date(2026, 7, 30)
    daily_rain = {"15": {date(2026, 7, 4): 0.0, date(2026, 6, 23): 22.1}}
    usable = _usable_communes(daily_rain, today)
    assert usable == {"15": date(2026, 7, 4)}


def test_stale_commune_is_excluded():
    today = date(2026, 7, 30)
    stale_date = date(2020, 2, 2)
    assert (today - stale_date).days > MAX_STALENESS_DAYS
    daily_rain = {"18": {stale_date: 1.0}}
    assert _usable_communes(daily_rain, today) == {}


def test_commune_with_no_rows_is_excluded():
    assert _usable_communes({"7": {}}, date(2026, 7, 30)) == {}


def test_uses_most_recent_date_per_commune():
    today = date(2026, 7, 30)
    daily_rain = {"21": {date(2026, 7, 1): 0.0, date(2026, 7, 4): 5.0, date(2026, 6, 1): 10.0}}
    usable = _usable_communes(daily_rain, today)
    assert usable == {"21": date(2026, 7, 4)}
