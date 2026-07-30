"""Tests for evaluation/ablation.py — specs/007-experimental-eval/spec.md task 4.

Pure, no DB: hand-built AblationCase snapshots exercise the rules and
quality ablations directly.
"""

from __future__ import annotations

from domain.rules.facts import TerritorySnapshot
from evaluation.ablation import AblationCase, run_ablation


def test_rules_ablation_changes_level_when_a_floor_rule_fired():
    # Low neural score, but the slope+rain floor rule pushes it to "alto".
    case = AblationCase(
        commune_id="8",
        neural_score=0.1,
        snapshot=TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0),
    )
    result = run_ablation("rules", [case])
    assert result.n_cases == 1
    assert result.n_level_changed == 1
    assert result.examples[0].full_level == "alto"
    assert result.examples[0].ablated_level == "bajo"


def test_rules_ablation_no_change_when_no_rule_fires():
    case = AblationCase(
        commune_id="1",
        neural_score=0.5,
        snapshot=TerritorySnapshot(commune_id="1", precip_72h_mm=5.0),
    )
    result = run_ablation("rules", [case])
    assert result.n_level_changed == 0


def test_quality_ablation_changes_confidence_not_level():
    flagged = TerritorySnapshot(
        commune_id="8", precip_72h_mm=5.0, swi_pct=10.0, quality_flags=frozenset({"frozen_signal"})
    )
    case = AblationCase(commune_id="8", neural_score=0.3, snapshot=flagged)
    result = run_ablation("quality", [case])
    # Removing the flag should raise confidence (full had the penalty, ablated doesn't).
    assert result.confidence_delta_mean < 0  # full - ablated is negative: full was lower


def test_unknown_target_raises():
    import pytest

    with pytest.raises(ValueError):
        run_ablation("ontology", [])  # type: ignore[arg-type]


def test_examples_capped_at_max_examples():
    cases = [
        AblationCase(
            commune_id=str(i),
            neural_score=0.1,
            snapshot=TerritorySnapshot(commune_id=str(i), slope_p90_deg=40.0, precip_72h_mm=150.0),
        )
        for i in range(10)
    ]
    result = run_ablation("rules", cases, max_examples=3)
    assert result.n_level_changed == 10
    assert len(result.examples) == 3


def test_pct_level_changed():
    cases = [
        AblationCase(
            commune_id="1",
            neural_score=0.5,
            snapshot=TerritorySnapshot(commune_id="1", precip_72h_mm=5.0),
        ),
        AblationCase(
            commune_id="8",
            neural_score=0.1,
            snapshot=TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0),
        ),
    ]
    result = run_ablation("rules", cases)
    assert result.pct_level_changed == 0.5
