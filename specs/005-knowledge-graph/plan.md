# SPEC-005 — plan.md

## Architecture

New top-level `kg/` package, same status as `ml/` or `scraper/` — I/O-heavy, imports `domain/` and
`infrastructure/repositories/`.

## Files touched

- `kg/__init__.py`, `kg/build.py` — A-Box population.
- `kg/queries/exposed_facilities.sparql`, `kg/queries/upslope_neighbours.sparql`,
  `kg/queries/shared_stream_recent_event.sparql`.
- `kg/export_cypher.py` — optional Neo4j visualization export.
- `alerts/evacuation.py` — extend Overpass query for hospitals/clinics.
- `db/models/critical_facility.py` — new table + Alembic migration.

## Interfaces

```python
async def build_graph(session: AsyncSession) -> rdflib.Graph: ...
def run_query(graph: rdflib.Graph, name: str, **bindings) -> list[dict]: ...
```

## Sequencing

Depends on SPEC-001 (ontology classes/properties as the RDF schema) and reuses
`infrastructure/repositories/landslide_events.py`. Can run in parallel with SPEC-006. Feeds
spatial predicates back into SPEC-002's `TerritorySnapshot` (`nearest_critical_facility_m`).
