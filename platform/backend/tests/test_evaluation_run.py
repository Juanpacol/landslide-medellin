"""Tests for evaluation/run.py — the four-arm comparison harness.

Focus: showing the arms actually disagree on a case where the audit's motivating gap applies
(a low neural score on a geotechnically dangerous territory), which is the point of building a
neuro-symbolic arm at all.
"""

from __future__ import annotations

from domain.rules.facts import TerritorySnapshot
from evaluation.run import ARMS, arms_disagree, run_all_arms, run_arm


def test_all_four_arms_run_without_error():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    results = run_all_arms("8", 0.1, snapshot)
    assert set(results.keys()) == set(ARMS)


def test_ml_only_and_declared_index_ignore_rules():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    ml_result = run_arm("ml_only", "8", 0.1, snapshot)
    declared_result = run_arm("declared_index", "8", 0.1, snapshot)
    assert ml_result.used_rules is False
    assert declared_result.used_rules is False
    assert ml_result.level == "bajo"  # 0.1 -> bajo, no rule ever raises it in this arm


def test_neurosymbolic_arm_disagrees_with_ml_only_when_rules_fire():
    # The exact motivating case: low neural score, but slope+rain rule floors it to alto.
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    results = run_all_arms("8", 0.1, snapshot)
    assert results["ml_only"].level == "bajo"
    assert results["neurosymbolic"].level == "alto"
    assert arms_disagree(results) is True


def test_arms_agree_when_no_rule_fires():
    snapshot = TerritorySnapshot(commune_id="11", precip_72h_mm=5.0)
    results = run_all_arms("11", 0.5, snapshot)
    assert results["ml_only"].level == results["neurosymbolic"].level == "medio"


def test_rules_only_arm_has_no_score():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    result = run_arm("rules_only", "8", 0.9, snapshot)  # neural_score ignored by this arm
    assert result.score is None
    assert result.level == "alto"  # from the rule floor alone
