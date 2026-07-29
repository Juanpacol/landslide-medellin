"""Tests for the pure rule engine (domain/rules/engine.py).

Focus: purity (same snapshot -> same trace), priority ordering, and that Veto/SetFloor/Escalate
are distinguishable effect types the inference engine (SPEC-003) can dispatch on.
"""

from __future__ import annotations

from domain.rules.engine import Escalate, RaisePriority, Rule, SetFloor, Veto, evaluate
from domain.rules.facts import TerritorySnapshot

_RULES = (
    Rule(
        id="R-LOW",
        description="fires when a is set",
        priority=1,
        condition=lambda s: s.slope_p90_deg is not None,
        effect=Escalate(steps=1),
        provenance="test",
    ),
    Rule(
        id="R-HIGH",
        description="fires when b is set",
        priority=10,
        condition=lambda s: s.twi_p90 is not None,
        effect=SetFloor(level="alto"),
        provenance="test",
    ),
    Rule(
        id="R-NEVER",
        description="never evaluable without ndvi",
        priority=5,
        condition=lambda s: None if s.ndvi_min is None else s.ndvi_min < 0,
        effect=RaisePriority(),
        provenance="test",
    ),
)


def test_purity_same_snapshot_same_trace():
    snap = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, twi_p90=12.0)
    t1 = evaluate(snap, _RULES)
    t2 = evaluate(snap, _RULES)
    assert t1 == t2


def test_priority_ordering_highest_first():
    snap = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, twi_p90=12.0)
    trace = evaluate(snap, _RULES)
    assert [r.id for r in trace.fired] == ["R-HIGH", "R-LOW"]


def test_not_evaluable_when_input_missing():
    snap = TerritorySnapshot(commune_id="8")
    trace = evaluate(snap, _RULES)
    assert trace.fired == ()
    assert {r.id for r in trace.not_evaluable} == {"R-NEVER"}
    assert {r.id for r in trace.not_fired} == {"R-LOW", "R-HIGH"}


def test_not_fired_when_condition_false():
    snap = TerritorySnapshot(commune_id="8", ndvi_min=0.5)
    trace = evaluate(snap, _RULES)
    assert any(r.id == "R-NEVER" for r in trace.not_fired)


def test_veto_is_a_distinct_effect_type():
    rule = Rule(
        id="R-VETO",
        description="vetoes",
        priority=1000,
        condition=lambda s: True,
        effect=Veto(reason="no_signal"),
        provenance="test",
    )
    trace = evaluate(TerritorySnapshot(commune_id="1"), (rule,))
    assert isinstance(trace.fired[0].effect, Veto)
    assert trace.fired[0].effect.reason == "no_signal"
