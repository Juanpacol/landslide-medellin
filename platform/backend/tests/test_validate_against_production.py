"""Tests for evaluation/validate_against_production.py's pure snapshot-construction logic —
no DB, no network. The script's `collect_real_results()` itself needs a real Supabase
connection and is exercised by hand (see docs/research/production_validation_2026-07-30.md),
not in CI; this test covers the one piece that's DB-free: mapping a `CommuneHazard`-shaped
object into a `TerritorySnapshot`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evaluation.validate_against_production import _build_snapshot


@dataclass(frozen=True)
class _FakeHazard:
    """Minimal stand-in for ml.hazard.CommuneHazard — only the fields
    _build_snapshot() reads."""

    susceptibility_components: dict
    trigger_components: dict = field(default_factory=dict)


def test_maps_hazard_fraction_and_swi_correctly():
    hazard = _FakeHazard(
        susceptibility_components={"hazard": 0.6},
        trigger_components={"swi": 0.5, "antecedent": 12.3, "seismic": 0.1},
    )
    snap = _build_snapshot("8", hazard, prior_event_count=2, rain_is_frozen=False)
    assert snap.commune_id == "8"
    assert snap.hazard_fraction == 0.6
    assert snap.swi_pct == 50.0  # 0.5 * 100
    assert snap.antecedent_mm == 12.3
    assert snap.seismic_intensity == 0.1
    assert snap.prior_event_count == 2
    assert snap.quality_flags == frozenset()


def test_frozen_signal_flag_is_propagated():
    hazard = _FakeHazard(susceptibility_components={}, trigger_components={})
    snap = _build_snapshot("1", hazard, prior_event_count=0, rain_is_frozen=True)
    assert snap.quality_flags == frozenset({"frozen_signal"})


def test_missing_swi_stays_none_not_zero():
    # swi=None must map to swi_pct=None, never a silent 0.0 (the exact discipline
    # domain/susceptibility.py and domain/rules/facts.py both document).
    hazard = _FakeHazard(
        susceptibility_components={"hazard": None}, trigger_components={"swi": None}
    )
    snap = _build_snapshot("12", hazard, prior_event_count=0, rain_is_frozen=False)
    assert snap.swi_pct is None
    assert snap.hazard_fraction is None


def test_slope_twi_ndvi_are_honestly_none():
    # barrio_terrain is empty in production as of this session — must never be
    # fabricated as a value.
    hazard = _FakeHazard(susceptibility_components={"hazard": 0.3}, trigger_components={})
    snap = _build_snapshot("1", hazard, prior_event_count=0, rain_is_frozen=False)
    assert snap.slope_p90_deg is None
    assert snap.twi_p90 is None
    assert snap.ndvi_min is None
    assert snap.nearest_critical_facility_m is None
