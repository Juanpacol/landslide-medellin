"""Pure data-quality predicates, shared by `monitoring/scraper_validator.py` (I/O: runs them
against live queries and posts to Slack) and `domain/rules/catalog.py` (uses them, via
`TerritorySnapshot.quality_flags`, to decide whether a hazard score of zero means "no signal" or
"confirmed no risk" — see `domain/rules/catalog.py::R_QUAL_01`).

Before this module, the plausibility checks in `scraper_validator.py` lived only as inline
comparisons inside async DB queries. Splitting the pure comparison from the I/O means the same
definition of "frozen signal" or "implausible max" cannot silently drift between the monitor and
the reasoner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Same thresholds as `monitoring/scraper_validator.py` — kept here as the single definition.
MIN_DISTINCT_VALUES = 3
MIN_ROWS_FOR_DISTINCT_CHECK = 50
MIN_PLAUSIBLE_MAX_MM = 1.0
MAX_PLAUSIBLE_DAILY_MM = 400.0
SEISMIC_STALE_DAYS = 30


def is_frozen_signal(values: list[float], *, min_rows: int = MIN_ROWS_FOR_DISTINCT_CHECK) -> bool:
    """True if a series of `min_rows`+ readings collapses to too few distinct values.

    A healthy feed varies (different stations, different times). Two or fewer distinct
    values across hundreds of readings is the signature of a stuck field, not a measurement —
    the exact bug that zeroed out TEYVA's rain trigger (audit finding 2, 2026-07-29).
    """
    if len(values) < min_rows:
        return False
    return len({round(v, 6) for v in values}) < MIN_DISTINCT_VALUES


def is_implausibly_low_max(window_max_mm: float, window_rows: int) -> bool:
    """True if the maximum reading across a long window is suspiciously near zero.

    Medellín has dry seasons, so a single dry day is normal. Two weeks where NO commune tops
    1mm is not — the city averages ~4-5mm/day.
    """
    if window_rows < MIN_ROWS_FOR_DISTINCT_CHECK:
        return False
    return window_max_mm < MIN_PLAUSIBLE_MAX_MM


def is_implausibly_high_daily(daily_max_mm: float) -> bool:
    """True if a daily rainfall figure exceeds what's physically possible.

    World record is ~1,825mm/24h; anything over 400mm/day in Medellín is a unit error or a
    cumulative counter summed as if it were a daily value.
    """
    return daily_max_mm > MAX_PLAUSIBLE_DAILY_MM


def is_stale(days_since_last_reading: int, *, threshold_days: int = SEISMIC_STALE_DAYS) -> bool:
    """True if a feed hasn't produced a new reading in longer than expected.

    `records_valid=0` with status `ok` is indistinguishable from "the parser broke" unless
    staleness is checked explicitly.
    """
    return days_since_last_reading > threshold_days


@dataclass(frozen=True)
class DataQualityScore:
    """Coverage and plausibility flags for one source, for one commune.

    `coverage` is the fraction of expected readings actually present (0-1); `flags` are the
    plausibility problems detected (e.g. `"frozen_signal"`, `"implausible_max"`). An empty
    `flags` with `coverage < 1.0` still means "trust this less" — the two are independent axes.
    """

    source: str
    commune_id: str
    coverage: float
    flags: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_trustworthy(self) -> bool:
        return self.coverage > 0.0 and not self.flags
