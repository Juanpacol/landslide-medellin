"""Tests for domain/quality.py — the pure predicates shared by scraper_validator.py and the
rule engine, so they cannot silently drift (specs/002-rule-engine/spec.md criterion 5)."""

from __future__ import annotations

from domain.quality import (
    DataQualityScore,
    is_frozen_signal,
    is_implausibly_high_daily,
    is_implausibly_low_max,
    is_stale,
)


def test_frozen_signal_detects_two_values_across_many_rows():
    values = [0.0] * 400 + [0.003] * 100
    assert is_frozen_signal(values) is True


def test_frozen_signal_false_with_enough_variety():
    values = [float(i % 40) / 10 for i in range(200)]
    assert is_frozen_signal(values) is False


def test_frozen_signal_false_below_min_rows():
    assert is_frozen_signal([0.0, 0.003]) is False


def test_implausibly_low_max_true_when_max_near_zero_over_long_window():
    assert is_implausibly_low_max(window_max_mm=0.003, window_rows=500) is True


def test_implausibly_low_max_false_short_window():
    assert is_implausibly_low_max(window_max_mm=0.0, window_rows=10) is False


def test_implausibly_high_daily_true_over_world_record_scale():
    assert is_implausibly_high_daily(92.2) is False
    assert is_implausibly_high_daily(450.0) is True


def test_is_stale_true_past_threshold():
    assert is_stale(45) is True
    assert is_stale(10) is False


def test_data_quality_score_is_trustworthy():
    good = DataQualityScore(source="siata", commune_id="8", coverage=1.0)
    bad = DataQualityScore(source="siata", commune_id="8", coverage=1.0, flags=frozenset({"frozen_signal"}))
    empty = DataQualityScore(source="siata", commune_id="8", coverage=0.0)
    assert good.is_trustworthy is True
    assert bad.is_trustworthy is False
    assert empty.is_trustworthy is False
