"""Tests for application/neurosymbolic/explain.py — deterministic derivation rendering and the
faithfulness check that keeps agent/risk_explanations.py from inventing factors.
"""

from __future__ import annotations

from application.neurosymbolic.explain import is_faithful, render
from application.neurosymbolic.infer import resolve_verdict
from domain.rules.facts import TerritorySnapshot


def test_render_includes_one_node_per_fired_rule_plus_neural_and_confidence():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.1, snapshot)
    tree = render(verdict)

    kinds = [n.kind for n in tree.nodes]
    assert "neural" in kinds
    assert "confidence" in kinds
    assert "rule" in kinds  # R-GEO-01 fires
    assert "conflict" in kinds  # the floor override is recorded


def test_render_all_four_risk_levels():
    for score in (0.1, 0.5, 0.8, 0.95):
        snapshot = TerritorySnapshot(commune_id="1", precip_72h_mm=5.0)
        verdict = resolve_verdict("1", score, snapshot)
        tree = render(verdict)
        assert len(tree.nodes) >= 2  # at least neural + confidence


def test_render_is_deterministic():
    snapshot = TerritorySnapshot(
        commune_id="9", slope_p90_deg=30.0, swi_pct=90.0, precip_72h_mm=5.0
    )
    verdict = resolve_verdict("9", 0.2, snapshot)
    tree1 = render(verdict)
    tree2 = render(verdict)
    assert tree1 == tree2


def test_veto_produces_a_conflict_node_referencing_the_veto_rule():
    snapshot = TerritorySnapshot(commune_id="1")
    verdict = resolve_verdict("1", 0.6, snapshot)
    tree = render(verdict)
    assert any(n.source_id == "R-QUAL-01" and n.kind == "conflict" for n in tree.nodes)


def test_faithfulness_accepts_real_source_ids():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.1, snapshot)
    tree = render(verdict)
    assert is_faithful(["neural", "R-GEO-01"], tree) is True


def test_faithfulness_rejects_invented_source():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.1, snapshot)
    tree = render(verdict)
    assert is_faithful(["neural", "R-GHOST-99"], tree) is False
