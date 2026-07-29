# SPEC-001 — Territory Ontology (OWL)

## Problem

TEYVA has no formal model of the domain. Territory, terrain, triggers and exposure are scattered
across dataclasses, DB columns and hardcoded dicts (some duplicated and wrong — see
`agent/risk_explanations.py::_IS_LADERA`). A neuro-symbolic system needs a shared, machine-readable
vocabulary that both the rule engine and the knowledge graph can reference.

## Goal

An OWL ontology (`ontology/teyva.owl`) formally defining the domain: territories, terrain
features, triggers, exposure, historical events and hazard assessments — authored in Protégé,
loaded at runtime via `owlready2`, queryable via `rdflib`/SPARQL.

## Non-goals

- Executing SWRL rules at runtime (SPEC-002 owns the executable rule engine; SWRL here is the
  formal specification only).
- A Neo4j service (SPEC-005 handles the knowledge graph; Cypher export is optional and visual-only).

## Acceptance criteria

1. `ontology/teyva.owl` loads without errors via `owlready2` and is logically consistent.
2. Every commune/corregimiento in `domain/communes.py::COMMUNES` has a corresponding OWL
   individual, generated from that module (not hand-typed).
3. Datatype properties match existing DB column names exactly (`slope_p90_deg`, `twi_p90`, etc.).
4. Every geotechnical rule planned for SPEC-002 has a matching SWRL axiom, and a test asserts
   this correspondence so the two cannot silently drift.
5. `infrastructure/ontology/loader.py` provides `ontology_version()` and
   `individuals_for_commune(id)`.
