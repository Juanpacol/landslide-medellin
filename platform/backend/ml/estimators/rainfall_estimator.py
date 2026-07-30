"""Rainfall estimator — wraps the trigger inputs already normalized in
`domain/susceptibility.py::trigger_breakdown` (SWI and antecedent precipitation) into a `Signal`.
Does not recompute the normalization; that logic stays declared once, in `domain/susceptibility.py`.
"""

from __future__ import annotations

from domain.risk_rules import ANTECEDENT_INDEX_THRESHOLD_MM as _ANTECEDENT_REF
from domain.rules.facts import TerritorySnapshot
from domain.susceptibility import trigger_breakdown as _trigger_breakdown
from ml.estimators.base import Signal


def estimate_rainfall(snapshot: TerritorySnapshot) -> Signal:
    """Normalized rainfall-trigger signal (SWI + antecedent precipitation) for a commune."""
    parts = _trigger_breakdown(
        soil_water_index_pct=snapshot.swi_pct,
        antecedent_precip_mm=snapshot.antecedent_mm,
        antecedent_reference_mm=_ANTECEDENT_REF,
    )
    rain = parts["rain"]
    inputs = (snapshot.swi_pct, snapshot.antecedent_mm)
    coverage = sum(1 for v in inputs if v is not None) / len(inputs)
    uncertainty = 0.0 if coverage == 1.0 else (0.5 if coverage > 0 else 1.0)
    return Signal(value=rain, uncertainty=uncertainty, source="rainfall", coverage=coverage)
