"""Tests for agent/risk_explanations.py::generate_explanation_from_verdict —
the derivation-grounded explanation path from SPEC-004: no LLM call, every
factor is a derivation node's text verbatim, so faithfulness holds by
construction.
"""

from __future__ import annotations

from agent.risk_explanations import generate_explanation_from_verdict
from application.neurosymbolic.explain import render
from application.neurosymbolic.infer import resolve_verdict
from domain.rules.facts import TerritorySnapshot


def test_factors_are_verbatim_derivation_node_text():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.1, snapshot)
    tree = render(verdict)
    node_texts = {n.text for n in tree.nodes}

    _, generated_by, structured = generate_explanation_from_verdict(verdict)

    assert generated_by == "derivation"
    for factor in structured["factors"]:
        assert factor in node_texts


def test_no_llm_no_api_key_needed(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    snapshot = TerritorySnapshot(commune_id="9", slope_p90_deg=30.0, swi_pct=90.0, precip_72h_mm=5.0)
    verdict = resolve_verdict("9", 0.2, snapshot)
    text, generated_by, _ = generate_explanation_from_verdict(verdict)
    assert generated_by == "derivation"
    assert text


def test_urgency_matches_verdict_level():
    snapshot = TerritorySnapshot(commune_id="1", precip_72h_mm=5.0)
    for score, expected_level in ((0.1, "bajo"), (0.5, "medio")):
        verdict = resolve_verdict("1", score, snapshot)
        _, _, structured = generate_explanation_from_verdict(verdict)
        assert structured["urgency"] == expected_level


def test_veto_case_still_produces_factors():
    # No trigger signal at all: R-QUAL-01 vetoes.
    snapshot = TerritorySnapshot(commune_id="1")
    verdict = resolve_verdict("1", 0.6, snapshot)
    _, _, structured = generate_explanation_from_verdict(verdict)
    assert structured["factors"]


def test_deterministic_same_verdict_same_output():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.1, snapshot)
    r1 = generate_explanation_from_verdict(verdict)
    r2 = generate_explanation_from_verdict(verdict)
    assert r1 == r2
