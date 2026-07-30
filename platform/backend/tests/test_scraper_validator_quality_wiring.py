"""Regression test for monitoring/scraper_validator.py's SPEC-002 wiring
(specs/002-rule-engine/spec.md criterion 5): the validator's plausibility
thresholds must come from domain/quality.py, not a second, independently
maintained copy — the exact kind of drift the audit's rain-corruption
finding could have been caught earlier by, had the two definitions not
been able to diverge silently.

No DB/AsyncSession here: monitoring/scraper_validator.py's async functions
need a real session and aren't unit-testable in isolation without one (no
existing test harness for that in this repo). This test instead verifies
the import wiring and that domain/quality.py's predicates reproduce the
exact behavior the validator used to hardcode inline.
"""

from __future__ import annotations

from domain.quality import (
    MAX_PLAUSIBLE_DAILY_MM,
    MIN_PLAUSIBLE_MAX_MM,
    MIN_ROWS_FOR_DISTINCT_CHECK,
    SEISMIC_STALE_DAYS,
    is_frozen_signal,
    is_implausibly_high_daily,
    is_implausibly_low_max,
    is_stale,
)
from monitoring import scraper_validator


def test_validator_imports_thresholds_from_domain_quality_not_a_copy():
    assert scraper_validator.MIN_PLAUSIBLE_MAX_MM is MIN_PLAUSIBLE_MAX_MM
    assert scraper_validator.MIN_ROWS_FOR_DISTINCT_CHECK is MIN_ROWS_FOR_DISTINCT_CHECK
    assert scraper_validator.MAX_PLAUSIBLE_DAILY_MM is MAX_PLAUSIBLE_DAILY_MM
    assert scraper_validator.SEISMIC_STALE_DAYS is SEISMIC_STALE_DAYS


def test_frozen_signal_reproduces_the_original_2026_07_29_incident():
    # The real values from the audit: 7890 zeros + 851 copies of 0.003.
    values = [0.0] * 7890 + [0.003] * 851
    assert is_frozen_signal(values, min_rows=MIN_ROWS_FOR_DISTINCT_CHECK) is True


def test_implausibly_low_max_reproduces_the_original_incident():
    # Max reading across 20 communes over 25 days was 0.003mm.
    assert is_implausibly_low_max(window_max_mm=0.003, window_rows=8741) is True


def test_implausibly_high_daily_reproduces_the_92mm_incident():
    assert is_implausibly_high_daily(92.202) is False  # below the 400mm threshold
    assert is_implausibly_high_daily(450.0) is True


def test_seismic_staleness_reproduces_the_93_run_incident():
    # The feed went 5 months (~150 days) with no new event while the scraper reported ok.
    assert is_stale(150, threshold_days=SEISMIC_STALE_DAYS) is True
    assert is_stale(5, threshold_days=SEISMIC_STALE_DAYS) is False
