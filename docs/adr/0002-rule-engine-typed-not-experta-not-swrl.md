# ADR-0002 — Typed rule engine in `domain/rules/`, not experta, not SWRL runtime

## Context

The rule engine needs to evaluate geotechnical/expert rules against territory data. Candidates:
`experta` (a CLIPS/PyKnow-style RETE engine), executing SWRL axioms directly via `owlready2` +
Pellet, or a small hand-written typed engine.

## Decision

Build a pure, typed, forward-chaining engine in `domain/rules/engine.py`. SWRL axioms in
`ontology/teyva.owl` (SPEC-001) remain the formal specification, cross-checked against the rule
catalog by a test, but are not executed at runtime.

## Consequences

- `experta` rejected: last released 2018, fragile on Python 3.11, and its `Fact` objects do not
  integrate with the typed `TerritorySnapshot` used across `domain/` and `application/`.
- SWRL+Pellet rejected as the runtime: requires a JVM in every container and GitHub Actions cron,
  slow, and hard to debug against a production incident.
- The typed engine is zero-dependency, fully unit-testable without any I/O, and matches the
  existing `domain/` convention (`risk_rules.py`, `susceptibility.py`).
- Trade-off: two representations of the same rules (OWL/SWRL and `catalog.py`) that could drift.
  Mitigated by the SPEC-001 cross-check test — every SWRL axiom must have a matching `Rule.id`.
