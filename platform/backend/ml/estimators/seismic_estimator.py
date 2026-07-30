"""Seismic estimator — wraps `domain/susceptibility.py`'s seismic normalization
(`SEISMIC_SATURATION`) into a `Signal`. Seismic activity modulates the rain trigger rather than
triggering alone (see `domain/susceptibility.py::trigger_breakdown` docstring); as an independent
estimator it still needs its own uncertainty, since the modulation role doesn't change how
confident we are in the raw seismic-intensity reading itself.
"""

from __future__ import annotations

from domain.rules.facts import TerritorySnapshot
from domain.susceptibility import SEISMIC_SATURATION, _clamp01
from ml.estimators.base import Signal


def estimate_seismic(snapshot: TerritorySnapshot) -> Signal:
    intensity = snapshot.seismic_intensity
    if intensity is None:
        return Signal(value=None, uncertainty=1.0, source="seismic", coverage=0.0)
    normalized = round(_clamp01(intensity / SEISMIC_SATURATION), 4)
    return Signal(value=normalized, uncertainty=0.0, source="seismic", coverage=1.0)
