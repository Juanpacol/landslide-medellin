# SPEC-005 — Knowledge Graph

## Problem

Territory relationships (adjacency, drainage, exposure) are not modeled anywhere — they are
implicit in separate tables (`barrio_terrain`, `barrio_hazard`, `safe_zones`, `seismic_events`).
Rules like "hospital within 200m" or "shares a stream with a recent event" have no data to query
against.

## Goal

A knowledge graph (`kg/`), populated from Postgres into RDF, with named SPARQL queries the rule
engine can call for spatial predicates — runtime infrastructure, not a visualization demo.

## Non-goals

- A Neo4j service in docker-compose (Cypher export is optional, visual-only, no sync obligation).

## Acceptance criteria

1. `kg/build.py` populates the A-Box from territories, barrios, `barrio_terrain`, `barrio_hazard`,
   `safe_zones`, `seismic_events`, and non-synthetic `landslide_events` (reusing the existing
   `is_synthetic` filter in `infrastructure/repositories/landslide_events.py`).
2. `alerts/evacuation.py`'s Overpass query extended to fetch `amenity=hospital|clinic`, persisted
   as `CriticalFacility` individuals.
3. Adjacency (`adjacentTo`) and `drainedBy` computed from barrio polygons via `shapely`.
4. Named SPARQL queries exist for: exposed critical facilities under high hazard; upslope
   neighbours of a territory; territories sharing a stream with a recent event.
5. Node/edge counts match SQL source-of-truth counts; no orphan territory.
