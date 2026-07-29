# SPEC-001 — plan.md

## Architecture

Ontology file lives at repo root under `ontology/` (a research artifact, not backend code).
Loading is I/O (`infrastructure/ontology/loader.py`); `domain/` never imports owlready2 directly.

## Files touched

- `ontology/teyva.owl` — the T-Box + individuals, authored in Protégé.
- `ontology/README.md` — class/property reference, notes SWRL axioms as non-executable spec.
- `infrastructure/ontology/loader.py` — cached load, `ontology_version()`, `individuals_for_commune()`.
- `infrastructure/ontology/generate_individuals.py` — script regenerating the 21 territory
  individuals from `domain/communes.py::COMMUNES` (run manually when communes change, output
  copied into the `.owl` file's A-Box section).
- `docs/adr/0001-ontology-owl-not-neo4j.md`.

## Interfaces

```python
def ontology_version() -> str: ...
def individuals_for_commune(commune_id: str) -> dict[str, Any]: ...
```

## Sequencing

No dependencies (can run in parallel with SPEC-000 translation, authored in English directly).
Blocks SPEC-002's SWRL cross-check test and SPEC-005 (knowledge graph A-Box).
