"""Tests for evaluation/stability.py — counterfactual stability under ±5% rain perturbation.

Pure, no DB: hand-built StabilityCase snapshots exercise resolve_verdict twice per case.
"""

from __future__ import annotations

import pytest

from domain.rules.catalog import CATALOG
from domain.rules.facts import TerritorySnapshot
from evaluation.stability import StabilityCase, counterfactual_stability


def test_case_without_rain_fields_is_excluded_from_denominator():
    case = StabilityCase(
        commune_id="1", neural_score=0.3, snapshot=TerritorySnapshot(commune_id="1")
    )
    result = counterfactual_stability([case], CATALOG)
    assert result.n_cases == 1
    assert result.n_eligible == 0
    assert result.pct_level_changed == 0.0


def test_stable_case_far_from_any_threshold_does_not_flip():
    # precip_72h_mm well below R-GEO-01's 120mm threshold even after +5%.
    case = StabilityCase(
        commune_id="1",
        neural_score=0.2,
        snapshot=TerritorySnapshot(commune_id="1", slope_p90_deg=40.0, precip_72h_mm=10.0),
    )
    result = counterfactual_stability([case], CATALOG)
    assert result.n_eligible == 1
    assert result.n_level_changed == 0
    assert result.examples == ()


def test_case_straddling_a_rule_threshold_flips_and_is_recorded():
    # HEAVY_RAIN_72H_MM = 120.0 in domain/rules/catalog.py; 115mm * 1.05 = 120.75mm crosses it.
    case = StabilityCase(
        commune_id="8",
        neural_score=0.1,
        snapshot=TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=115.0),
    )
    result = counterfactual_stability([case], CATALOG)
    assert result.n_eligible == 1
    assert result.n_level_changed == 1
    assert result.pct_level_changed == 1.0
    assert len(result.examples) == 1
    assert result.examples[0].original_level != result.examples[0].perturbed_level


def test_veto_status_flip_is_tracked_separately_from_level():
    # antecedent_mm present but no other trigger signal — perturbing it keeps has_trigger_signal
    # true either way, so veto status should NOT flip here; this asserts the counter stays at 0
    # rather than conflating veto flips with level flips.
    case = StabilityCase(
        commune_id="5",
        neural_score=0.2,
        snapshot=TerritorySnapshot(commune_id="5", antecedent_mm=50.0),
    )
    result = counterfactual_stability([case], CATALOG)
    assert result.n_vetoed_changed == 0


def test_custom_perturbation_pct_is_applied():
    case = StabilityCase(
        commune_id="8",
        neural_score=0.1,
        snapshot=TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=100.0),
    )
    # 100 * 1.30 = 130mm crosses the 120mm floor threshold; +5% (105mm) would not.
    result_small = counterfactual_stability([case], CATALOG, perturbation_pct=0.05)
    result_large = counterfactual_stability([case], CATALOG, perturbation_pct=0.30)
    assert result_small.n_level_changed == 0
    assert result_large.n_level_changed == 1


def test_examples_capped_at_max_examples():
    cases = [
        StabilityCase(
            commune_id=str(i),
            neural_score=0.1,
            snapshot=TerritorySnapshot(commune_id=str(i), slope_p90_deg=40.0, precip_72h_mm=115.0),
        )
        for i in range(10)
    ]
    result = counterfactual_stability(cases, CATALOG, max_examples=3)
    assert result.n_level_changed == 10
    assert len(result.examples) == 3


def test_empty_cases_do_not_divide_by_zero():
    result = counterfactual_stability([], CATALOG)
    assert result.pct_level_changed == pytest.approx(0.0)
    assert result.pct_vetoed_changed == pytest.approx(0.0)
