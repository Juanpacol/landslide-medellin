"""
When two seismic reports are the SAME earthquake. Pure logic, no I/O.

## The problem

`seismic_events` stores reports, not earthquakes. A single physical
earthquake produces:

- K rows from SIATA — one per network station that recorded it;
- one row from USGS, with its own time/epicenter solution;
- one row from SGC, with another.

The previous dedup was by `(event_local_at.isoformat(), epicenter_label)`.
That only works within SIATA, where all rows for one earthquake share
identical computed time and label. Across agencies **it collapses zero
duplicates**: origin times differ by seconds and labels are different text
("12 km NE of Betulia, Colombia" vs SGC's municipality vs "Sismo en Medellín
- Antioquia").

And since `ml/seismic_features.py` computes a **Σ of magnitude²**, each
earthquake would count 2-3 times and the signal would inflate quadratically,
silently. That's why this is a prerequisite for integrating USGS/SGC, not a
later polish.

## Why these tolerances

Not round numbers picked at random:

- **±120 s.** ORIGIN time solutions across agencies agree within seconds.
  The margin is for SIATA, whose per-station `fecha_local` is a
  trigger/arrival timestamp: for a regional earthquake at 200-400 km, the
  S-wave arrives tens of seconds after origin. 120s covers that and stays
  well below the real spacing between felt earthquakes in Colombia.
- **60 km.** Epicenter solutions across agencies routinely differ by 10-40
  km, due to different station geometry and velocity models. 60km captures
  that without merging two distinct earthquakes on different faults.
- **|ΔM| ≤ 1.0.** Agencies report different scales (ML, Mw, Mb) that
  typically differ by 0.3-0.7. 1.0 is the honest bound. It's a **guard
  against absurd merges**, not the primary discriminant.
- **±45 s when lat/lon is missing.** Without geometry, tighten time instead
  of merging with a loose window.

## Precedence: SGC > USGS > SIATA

For the CANONICAL values of the earthquake. SGC is the national
seismological authority, so it has the best local solutions; USGS is
globally consistent and fast, but its epicenters in Colombia are coarser;
SIATA is a dense local network, irreplaceable for detecting small
earthquakes the other two miss, but its per-station published "epicenter" is
the least authoritative. Those local earthquakes form single-source
clusters, which is exactly correct.

The consensus magnitude is **the precedence winner's**, not the max or the
mean: the max biases upward (and the feature squares it, amplifying that)
and the mean mixes incompatible scales. This stays traceable via
`canonical_source`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.geo import distance_km

MATCH_TIME_WINDOW_S = 120.0
MATCH_DISTANCE_KM = 60.0
MATCH_MAGNITUDE_DELTA = 1.0
MATCH_TIME_ONLY_WINDOW_S = 45.0

# Index 0 = highest authority. An unknown source ranks below all of them.
SOURCE_PRECEDENCE: tuple[str, ...] = ("sgc", "usgs", "siata_sismos")


@dataclass(frozen=True)
class EventKey:
    """The minimum needed to decide whether two reports are the same earthquake.

    Deliberately NOT a SQLAlchemy model: that way these rules can be tested
    without a database, which is the part that will get tuned over time.
    """

    event_at: datetime
    source: str
    magnitude: float | None = None
    depth_km: float | None = None
    lat: float | None = None
    lon: float | None = None
    label: str | None = None

    @property
    def has_coords(self) -> bool:
        return self.lat is not None and self.lon is not None


def source_rank(source: str | None) -> int:
    """Position in the precedence order; lower wins. Unknown source goes last."""
    if not source:
        return len(SOURCE_PRECEDENCE)
    try:
        return SOURCE_PRECEDENCE.index(source)
    except ValueError:
        return len(SOURCE_PRECEDENCE)


def seconds_apart(a: EventKey, b: EventKey) -> float:
    return abs((a.event_at - b.event_at).total_seconds())


def km_apart(a: EventKey, b: EventKey) -> float | None:
    """Distance between epicenters, or None if either is missing coordinates."""
    if not (a.has_coords and b.has_coords):
        return None
    # Keyword-only on purpose: `haversine_km` is lon-first and swapping it
    # returns a wrong but plausible distance.
    return distance_km(lat1=a.lat, lon1=a.lon, lat2=b.lat, lon2=b.lon)  # type: ignore[arg-type]


def events_match(a: EventKey, b: EventKey) -> bool:
    """Are `a` and `b` reports of the same physical earthquake?"""
    # Magnitude only DISQUALIFIES; it never confirms on its own.
    if a.magnitude is not None and b.magnitude is not None:
        if abs(a.magnitude - b.magnitude) > MATCH_MAGNITUDE_DELTA:
            return False

    dt = seconds_apart(a, b)
    d_km = km_apart(a, b)
    if d_km is None:
        # No geometry on one side: tighten the time window instead.
        return dt <= MATCH_TIME_ONLY_WINDOW_S
    return dt <= MATCH_TIME_WINDOW_S and d_km <= MATCH_DISTANCE_KM


def pick_canonical(current: EventKey, candidate: EventKey) -> EventKey:
    """Which of the two contributes the cluster's canonical values.

    The higher-precedence source wins. On a tie, `current` is kept, so
    reprocessing doesn't change the result without reason.
    """
    return candidate if source_rank(candidate.source) < source_rank(current.source) else current


def best_match(candidate: EventKey, clusters: list[EventKey]) -> int | None:
    """Index of the cluster that best fits `candidate`, or None.

    Simple matching against each cluster's representative (no transitive
    closure over the raw rows): that way grouping doesn't depend on arrival
    order. If several fit, the closest in time wins; the final tiebreak is
    the lowest index, to keep it deterministic.
    """
    best_i: int | None = None
    best_dt = float("inf")
    for i, cluster in enumerate(clusters):
        if not events_match(candidate, cluster):
            continue
        dt = seconds_apart(candidate, cluster)
        if dt < best_dt:
            best_dt, best_i = dt, i
    return best_i


def merge_sources(existing: list[str], new_source: str) -> list[str]:
    """The cluster's list of sources, deduplicated and in precedence order."""
    merged = set(existing) | {new_source}
    return sorted(merged, key=lambda s: (source_rank(s), s))
