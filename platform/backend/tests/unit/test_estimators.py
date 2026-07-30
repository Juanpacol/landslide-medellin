"""Tests for ml/estimators/ — Signal protocol wrapping the existing declared normalizations
(specs/006-neural-estimators/spec.md). Pure: hand-built TerritorySnapshot, no DB.
"""

from __future__ import annotations

from domain.rules.facts import TerritorySnapshot
from ml.estimators.base import Signal
from ml.estimators.rainfall_estimator import estimate_rainfall
from ml.estimators.seismic_estimator import estimate_seismic
from ml.estimators.terrain_estimator import estimate_terrain
from ml.estimators.xgboost_estimator import estimate_from_prediction


def test_rainfall_no_data_returns_none_value_full_uncertainty():
    signal = estimate_rainfall(TerritorySnapshot(commune_id="1"))
    assert signal.value is None
    assert signal.uncertainty == 1.0
    assert signal.coverage == 0.0


def test_rainfall_full_coverage_zero_uncertainty():
    signal = estimate_rainfall(TerritorySnapshot(commune_id="1", swi_pct=50.0, antecedent_mm=40.0))
    assert signal.value is not None
    assert 0.0 <= signal.value <= 1.0
    assert signal.uncertainty == 0.0
    assert signal.coverage == 1.0


def test_seismic_no_data():
    signal = estimate_seismic(TerritorySnapshot(commune_id="1"))
    assert signal.value is None
    assert signal.uncertainty == 1.0


def test_seismic_normalizes_into_unit_interval():
    signal = estimate_seismic(TerritorySnapshot(commune_id="1", seismic_intensity=15.0))
    assert signal.value is not None
    assert 0.0 <= signal.value <= 1.0
    assert signal.uncertainty == 0.0


def test_terrain_uncertainty_reflects_coverage_gap():
    # Only hazard_fraction populated (today's typical case, per the terrain-ingestion gap).
    sparse = estimate_terrain(TerritorySnapshot(commune_id="1", hazard_fraction=0.5))
    rich = estimate_terrain(
        TerritorySnapshot(
            commune_id="1", hazard_fraction=0.5, slope_p90_deg=20.0, twi_p90=8.0, ndvi_min=0.4
        )
    )
    assert sparse.uncertainty > rich.uncertainty
    assert sparse.coverage < rich.coverage


def test_terrain_no_data_returns_none_value():
    signal = estimate_terrain(TerritorySnapshot(commune_id="1"))
    assert signal.value is None
    assert signal.coverage == 0.0


def test_all_estimators_return_signal_instances():
    snapshot = TerritorySnapshot(
        commune_id="1", swi_pct=50.0, seismic_intensity=5.0, hazard_fraction=0.3
    )
    for fn in (estimate_rainfall, estimate_seismic, estimate_terrain):
        assert isinstance(fn(snapshot), Signal)


def test_xgboost_no_prediction_returns_none_value():
    signal = estimate_from_prediction(None, None)
    assert signal.value is None
    assert signal.uncertainty == 1.0
    assert signal.coverage == 0.0


def test_xgboost_uncertainty_is_one_minus_confidence():
    signal = estimate_from_prediction(0.7, confidence=0.9)
    assert signal.value == 0.7
    assert signal.uncertainty == 0.1
    assert signal.coverage == 1.0


def test_xgboost_missing_confidence_is_full_uncertainty():
    signal = estimate_from_prediction(0.7, confidence=None)
    assert signal.value == 0.7
    assert signal.uncertainty == 1.0


def test_xgboost_clamps_score_to_unit_interval():
    signal = estimate_from_prediction(1.5, confidence=0.8)
    assert signal.value == 1.0
