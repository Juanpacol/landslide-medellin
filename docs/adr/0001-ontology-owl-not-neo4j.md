# ADR-0001 — Ontology in OWL (owlready2), not Neo4j

## Context

TEYVA needs a formal model of territory, terrain, triggers and exposure for the rule engine and
knowledge graph to share. Two candidates: an OWL ontology with a Python reasoner, or Neo4j as the
primary store.

## Decision

Author the ontology in Protégé as `ontology/teyva.owl`, commit it, load via `owlready2` for
reasoning and `rdflib` for SPARQL. Neo4j is not adopted as a service; an optional Cypher export
exists for visualization only (SPEC-005).

## Consequences

- No new infrastructure: no service to add to `docker-compose.yml`, no hosted instance for the 6
  GitHub Actions crons to reach.
- The `.owl` file is a citable, versionable research artifact — appropriate for a research
  contribution, not just an app dependency.
- Formal DL reasoning (consistency checks, SWRL as declarative spec) is available; Neo4j has
  neither.
- Trade-off: no native graph visualization or Cypher query ergonomics without the export step;
  accepted because SPEC-005's SPARQL queries cover the runtime need, and the export exists for the
  cases where a visual matters.
