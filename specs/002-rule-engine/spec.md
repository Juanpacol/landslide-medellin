# SPEC-002 — Rule Engine

## Problem

`domain/risk_rules.py` only maps a score to a category — no geotechnical or expert reasoning
happens. The audit (`docs/research/audit-2026-07.md` §5) found a real gap: `susceptibility × trigger`
silently returns 0 when data is missing, indistinguishable from "confirmed no risk". There is no
mechanism to say "slope > 35° and rain > 120mm ⇒ high, regardless of the neural score" or "a
hospital nearby raises priority."

## Goal

A pure, typed, forward-chaining rule engine under `domain/rules/` that evaluates geotechnical and
expert rules against a territory snapshot, producing a traceable, priority-ordered list of fired
(and not-evaluable) rules — with no I/O, fully unit-testable, and reusing existing declared
thresholds rather than introducing new ones.

## Non-goals

- Deciding the final risk verdict (SPEC-003 owns conflict resolution between neural score and
  rules).
- A general-purpose RETE engine or third-party library (`experta` is unmaintained; SWRL/Pellet
  needs a JVM in every cron — see ADR-0002 for the comparison, decision recorded there).

## Acceptance criteria

1. `Rule` is declarative: id, description, priority, condition, effect (`SetFloor`, `Escalate`,
   `MultiplyScore`, `RaisePriority`, `Veto`), provenance — never arbitrary code as the effect.
2. `evaluate(snapshot) -> RuleTrace` is a pure function: same input, same output; returns both
   fired rules (priority order) and rules that could not be evaluated for lack of data.
3. Rule catalog includes at minimum: slope+rain floor, slope+SWI escalation, TWI+antecedent
   escalation, NDVI+slope escalation, historical-proximity priority, critical-facility priority,
   seismic+SWI escalation, and a zero-coverage veto (the audit's "no signal ≠ no risk" gap).
4. Thresholds reuse `domain/susceptibility.py` and `domain/risk_rules.py` constants — no
   duplicated magic numbers.
5. `domain/quality.py::DataQualityScore` lifts the plausibility predicates already in
   `monitoring/scraper_validator.py` into pure functions, shared by both.
6. One test per rule (fires / does not fire / not evaluable); engine purity tested explicitly.
