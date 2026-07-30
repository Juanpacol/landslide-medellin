"""One test group per rule in domain/rules/catalog.py: fires / does not fire / not evaluable.

Verifies acceptance criterion 6 of specs/002-rule-engine/spec.md.
"""

from __future__ import annotations

from domain.rules.catalog import (
    CATALOG,
    R_EXPO_01,
    R_GEO_01,
    R_GEO_02,
    R_GEO_03,
    R_GEO_04,
    R_HIST_01,
    R_QUAL_01,
    R_SEIS_01,
)
from domain.rules.engine import Escalate, RaisePriority, SetFloor, Veto, evaluate
from domain.rules.facts import TerritorySnapshot


def test_r_geo_01_fires_on_steep_slope_and_heavy_rain():
    snap = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    assert R_GEO_01.evaluate(snap) is True
    assert isinstance(R_GEO_01.effect, SetFloor)


def test_r_geo_01_does_not_fire_below_threshold():
    snap = TerritorySnapshot(commune_id="8", slope_p90_deg=20.0, precip_72h_mm=150.0)
    assert R_GEO_01.evaluate(snap) is False


def test_r_geo_01_not_evaluable_without_data():
    snap = TerritorySnapshot(commune_id="8")
    assert R_GEO_01.evaluate(snap) is None


def test_r_geo_02_fires_on_moderate_slope_and_saturated_soil():
    snap = TerritorySnapshot(commune_id="8", slope_p90_deg=30.0, swi_pct=90.0)
    assert R_GEO_02.evaluate(snap) is True
    assert isinstance(R_GEO_02.effect, Escalate)


def test_r_geo_02_does_not_fire_dry_soil():
    snap = TerritorySnapshot(commune_id="8", slope_p90_deg=30.0, swi_pct=10.0)
    assert R_GEO_02.evaluate(snap) is False


def test_r_geo_03_fires_on_high_twi_and_antecedent():
    snap = TerritorySnapshot(commune_id="8", twi_p90=13.0, antecedent_mm=100.0)
    assert R_GEO_03.evaluate(snap) is True


def test_r_geo_03_not_evaluable_missing_twi():
    snap = TerritorySnapshot(commune_id="8", antecedent_mm=100.0)
    assert R_GEO_03.evaluate(snap) is None


def test_r_geo_04_fires_on_bare_soil_steep_slope():
    snap = TerritorySnapshot(commune_id="8", ndvi_min=0.05, slope_p90_deg=35.0)
    assert R_GEO_04.evaluate(snap) is True


def test_r_geo_04_does_not_fire_dense_vegetation():
    snap = TerritorySnapshot(commune_id="8", ndvi_min=0.8, slope_p90_deg=35.0)
    assert R_GEO_04.evaluate(snap) is False


def test_r_hist_01_fires_with_prior_events():
    snap = TerritorySnapshot(commune_id="8", prior_event_count=2)
    assert R_HIST_01.evaluate(snap) is True
    assert isinstance(R_HIST_01.effect, RaisePriority)


def test_r_hist_01_does_not_fire_zero_events():
    snap = TerritorySnapshot(commune_id="8", prior_event_count=0)
    assert R_HIST_01.evaluate(snap) is False


def test_r_expo_01_fires_near_critical_facility():
    snap = TerritorySnapshot(commune_id="8", nearest_critical_facility_m=50.0)
    assert R_EXPO_01.evaluate(snap) is True
    assert R_EXPO_01.effect.to == "max"


def test_r_expo_01_does_not_fire_far_facility():
    snap = TerritorySnapshot(commune_id="8", nearest_critical_facility_m=5000.0)
    assert R_EXPO_01.evaluate(snap) is False


def test_r_seis_01_fires_high_intensity_moderate_saturation():
    snap = TerritorySnapshot(commune_id="8", seismic_intensity=25.0, swi_pct=70.0)
    assert R_SEIS_01.evaluate(snap) is True


def test_r_seis_01_not_evaluable_missing_seismic():
    snap = TerritorySnapshot(commune_id="8", swi_pct=70.0)
    assert R_SEIS_01.evaluate(snap) is None


def test_r_qual_01_vetoes_zero_trigger_coverage():
    snap = TerritorySnapshot(commune_id="8")
    assert R_QUAL_01.evaluate(snap) is True
    assert isinstance(R_QUAL_01.effect, Veto)


def test_r_qual_01_does_not_fire_with_any_trigger_signal():
    snap = TerritorySnapshot(commune_id="8", precip_72h_mm=5.0)
    assert R_QUAL_01.evaluate(snap) is False


def test_r_qual_01_is_highest_priority_and_wins_ordering():
    snap = TerritorySnapshot(commune_id="8")
    trace = evaluate(snap, CATALOG)
    assert trace.fired[0].id == "R-QUAL-01"


def test_catalog_has_eight_rules_with_unique_ids():
    assert len(CATALOG) == 8
    assert len({r.id for r in CATALOG}) == 8
