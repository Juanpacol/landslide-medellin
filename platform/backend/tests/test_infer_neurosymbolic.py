"""Tests for application/neurosymbolic/infer.py::resolve_verdict — pure, no DB.

Covers specs/003-inference-engine/spec.md acceptance criteria: neural-only path, rule-override
path, veto path, confidence monotonicity.
"""

from __future__ import annotations

from application.neurosymbolic.infer import resolve_verdict
from domain.rules.facts import TerritorySnapshot


def test_neural_only_path_no_rules_fire():
    # Mild slope, light rain: no geotechnical rule should fire, level follows the neural score.
    snapshot = TerritorySnapshot(commune_id="11", slope_p90_deg=5.0, precip_72h_mm=10.0, swi_pct=20.0)
    verdict = resolve_verdict("11", 0.5, snapshot)
    assert verdict.level == "medio"  # risk_level_from_score(0.5): >=0.35 and <0.65 -> medio
    assert verdict.conflicts == ()
    assert verdict.derivation["fired_rules"] == []


def test_rule_floor_overrides_lower_neural_level():
    # Neural score is low ("bajo"), but slope+rain rule floors it to "alto".
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.1, snapshot)
    assert verdict.level == "alto"
    assert any(c["effect"] == "set_floor" for c in verdict.conflicts)


def test_rule_floor_never_lowered_by_high_neural_score():
    # Neural score alone would be "critico"; a floor rule can only raise, never lower — so a
    # high neural score plus a floor-alto rule should end at least at "alto", never below.
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.95, snapshot)
    assert verdict.level == "critico"  # neural already above the floor, floor is a no-op


def test_veto_path_zero_trigger_coverage():
    snapshot = TerritorySnapshot(commune_id="1")  # no rain, no swi, no seismic at all
    verdict = resolve_verdict("1", 0.6, snapshot)
    assert verdict.confidence == 0.0
    assert any(c["effect"] == "veto" for c in verdict.conflicts)
    assert verdict.derivation["vetoed"] is True


def test_escalation_raises_by_one_category():
    snapshot = TerritorySnapshot(commune_id="9", slope_p90_deg=30.0, swi_pct=90.0, precip_72h_mm=5.0)
    verdict = resolve_verdict("9", 0.2, snapshot)  # neural: bajo
    assert verdict.level == "medio"  # escalated one step from bajo


def test_confidence_monotonic_with_coverage():
    sparse = TerritorySnapshot(commune_id="8", precip_72h_mm=5.0)
    rich = TerritorySnapshot(
        commune_id="8",
        slope_p90_deg=20.0,
        twi_p90=8.0,
        ndvi_min=0.4,
        hazard_fraction=0.3,
        precip_72h_mm=5.0,
        antecedent_mm=10.0,
        swi_pct=30.0,
        seismic_intensity=5.0,
    )
    c_sparse = resolve_verdict("8", 0.3, sparse).confidence
    c_rich = resolve_verdict("8", 0.3, rich).confidence
    assert c_rich > c_sparse


def test_confidence_flags_reduce_confidence():
    clean = TerritorySnapshot(commune_id="8", precip_72h_mm=5.0, swi_pct=10.0)
    flagged = TerritorySnapshot(
        commune_id="8", precip_72h_mm=5.0, swi_pct=10.0, quality_flags=frozenset({"frozen_signal"})
    )
    assert resolve_verdict("8", 0.3, flagged).confidence < resolve_verdict("8", 0.3, clean).confidence


def test_priority_max_when_critical_facility_nearby():
    snapshot = TerritorySnapshot(commune_id="14", nearest_critical_facility_m=50.0, precip_72h_mm=5.0)
    verdict = resolve_verdict("14", 0.1, snapshot)
    assert verdict.priority == "max"
