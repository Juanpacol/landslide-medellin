"""Terrain estimator — wraps the static susceptibility components (slope, TWI, NDVI, official
hazard grade) already normalized in `domain/susceptibility.py::susceptibility_breakdown` into a
`Signal`. This is the estimator most exposed to the terrain-ingestion gap
(specs/006-neural-estimators/tasks.md): today only `hazard_fraction` is typically populated
(1 of 5 components), so `coverage` on this estimator is the honest way to see that gap without
reading a suspiciously confident single number.
"""

from __future__ import annotations

from domain.rules.facts import TerritorySnapshot
from domain.susceptibility import susceptibility_breakdown as _susceptibility_breakdown
from ml.estimators.base import Signal


def estimate_terrain(snapshot: TerritorySnapshot) -> Signal:
    breakdown = _susceptibility_breakdown(
        slope_p90_deg=snapshot.slope_p90_deg,
        twi_p90=snapshot.twi_p90,
        ndvi_min=snapshot.ndvi_min,
        hazard_fraction=snapshot.hazard_fraction,
    )
    uncertainty = round(1.0 - breakdown.coverage, 4)
    return Signal(
        value=breakdown.index,
        uncertainty=uncertainty,
        source="terrain",
        coverage=breakdown.coverage,
    )
