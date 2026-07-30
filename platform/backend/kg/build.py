"""Knowledge graph A-Box builder — populates an `rdflib.Graph` with territory individuals,
`adjacentTo` edges, and critical-facility exposure, queryable via SPARQL. `domain/rules/catalog.py`
rules that need spatial predicates (e.g. a future "upslope neighbour" rule) call `run_query()`,
not the DB directly — this is runtime infrastructure, not a visualization demo
(specs/005-knowledge-graph/spec.md).

Scope note vs. the original spec: full A-Box population from Postgres (barrio_terrain,
barrio_hazard, seismic_events, non-synthetic landslide_events) and polygon-based adjacency via
shapely are NOT implemented here — that needs an AsyncSession and the barrio polygon file, both
bigger asynchronous integration work. What IS implemented, DB-free: territory nodes (reusing
infrastructure/ontology/loader.py, so there's exactly one definition of "the 21 territories"), a
centroid-proximity approximation of `adjacentTo`, and REAL critical-facility data — hospitals and
clinics near each commune's centroid, fetched live from OpenStreetMap's public Overpass API (the
same source `alerts/evacuation.py` already uses for safe zones, no key required). "Shared
stream" data needs `landslide_events`/hydrography from Postgres and is NOT implemented; its query
file exists as the declared target, returning empty until that data is wired in.
"""

from __future__ import annotations

import logging
import time
from math import atan2, cos, radians, sin, sqrt
from typing import Any

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

logger = logging.getLogger(__name__)

TEYVA = Namespace("http://teyva.local/onto.owl#")

# How many nearest neighbours count as "adjacent" — a centroid-distance approximation of true
# polygon adjacency (which needs the barrio/comuna polygon file, not yet wired in).
ADJACENCY_K = 3

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Radius around each commune's centroid to search for hospitals/clinics. Generous on purpose:
# a centroid is not "the commune", and R-EXPO-01 (domain/rules/catalog.py) cares about proximity
# to the TERRITORY, not to one point in it.
FACILITY_SEARCH_RADIUS_M = 3000


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    x = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * atan2(sqrt(x), sqrt(1 - x))


def _territory_uri(commune_id: str) -> URIRef:
    return TEYVA[f"territory_{commune_id}"]


def build_static_graph(*, use_polygon_adjacency: bool = True) -> Graph:
    """Territories + adjacency. No network, no DB access — pulls from `domain/communes.py`
    (and, for adjacency, the checked-in barrio polygon GeoJSON) directly, so it can build (and
    be tested) offline. Does NOT include critical facilities: use `add_critical_facilities()`
    for that, separately, since it needs the network (Overpass API).

    Adjacency: TRUE polygon adjacency (`kg/polygon_adjacency.py`, shapely over
    `barrios-medellin.json`) for the 16 urban comunas that file covers, falling back to
    centroid-proximity (k nearest) for the 5 corregimientos it doesn't. Pass
    `use_polygon_adjacency=False` to get the old pure centroid-proximity graph for all 21
    (useful for comparison, or if the polygon file becomes unavailable).
    """
    from domain.communes import COMMUNES

    g = Graph()
    g.bind("teyva", TEYVA)

    for c in COMMUNES:
        uri = _territory_uri(c.id)
        cls = TEYVA.Corregimiento if c.tipo == "corregimiento" else TEYVA.Commune
        g.add((uri, RDF.type, cls))
        g.add((uri, TEYVA.canonical_id, Literal(c.id, datatype=XSD.string)))
        g.add((uri, TEYVA.official_code, Literal(c.official_code, datatype=XSD.string)))
        g.add((uri, TEYVA.nombre, Literal(c.nombre, datatype=XSD.string)))
        g.add((uri, TEYVA.is_ladera, Literal(c.is_ladera, datatype=XSD.boolean)))

    from domain.communes import CENTROIDS

    polygon_adj: dict[str, frozenset[str]] = {}
    if use_polygon_adjacency:
        try:
            from kg.polygon_adjacency import polygon_adjacency

            polygon_adj = polygon_adjacency()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Polygon adjacency unavailable, falling back to centroid-proximity for all communes: %s",
                exc,
            )

    for cid, centroid in CENTROIDS.items():
        if cid in polygon_adj:
            for other_id in polygon_adj[cid]:
                g.add((_territory_uri(cid), TEYVA.adjacentTo, _territory_uri(other_id)))
            continue

        # Centroid-proximity fallback: the 5 corregimientos (no barrio polygon coverage in
        # barrios-medellin.json — see kg/polygon_adjacency.py's module docstring), or all 21
        # if use_polygon_adjacency=False.
        distances = sorted(
            (
                (other_id, _haversine_km(centroid, other_centroid))
                for other_id, other_centroid in CENTROIDS.items()
                if other_id != cid
            ),
            key=lambda x: x[1],
        )
        for other_id, _dist in distances[:ADJACENCY_K]:
            g.add((_territory_uri(cid), TEYVA.adjacentTo, _territory_uri(other_id)))

    return g


def _fetch_facilities_near(lat: float, lon: float) -> list[dict[str, Any]]:
    """Hospitals/clinics within `FACILITY_SEARCH_RADIUS_M` of (lat, lon), via Overpass —
    same public, keyless API `alerts/evacuation.py::fetch_safe_zones_osm` already uses for
    parks/schools/stadiums. Synchronous (`requests`, not `httpx`): this module has no async
    caller today, and keeping it sync means `build_critical_facility_graph()` can run from a
    plain script (`python -m kg.build`) with no event loop.
    """
    import requests

    query = (
        f"[out:json][timeout:15];"
        f"(node[amenity~'^(hospital|clinic)$'](around:{FACILITY_SEARCH_RADIUS_M},{lat},{lon});"
        f"way[amenity~'^(hospital|clinic)$'](around:{FACILITY_SEARCH_RADIUS_M},{lat},{lon}););"
        f"out center;"
    )
    try:
        r = requests.post(OVERPASS_URL, data=query, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Overpass query failed for (%.4f, %.4f): %s", lat, lon, exc)
        return []

    out = []
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("amenity") or "unnamed"
        el_lat = el.get("lat") or (el.get("center") or {}).get("lat")
        el_lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if el_lat is None or el_lon is None:
            continue
        out.append(
            {
                "osm_id": f"{el.get('type')}/{el.get('id')}",
                "name": name,
                "amenity": tags.get("amenity"),
                "lat": el_lat,
                "lon": el_lon,
            }
        )
    return out


def add_critical_facilities(g: Graph, *, delay_s: float = 1.0) -> int:
    """Fetches hospitals/clinics near every commune centroid from Overpass and adds them to
    `g` as `CriticalFacility` individuals linked via `exposes`, feeding
    `exposed_facilities.sparql` and, eventually, `domain/rules/catalog.py::R_EXPO_01`'s real
    proximity data (today that rule's input is a caller-supplied distance, not this graph — see
    specs/005-knowledge-graph/tasks.md). Returns the number of facilities added. Does one
    Overpass call per commune (21 total); network-bound, not meant for the hot request path.
    A 1s pause between calls respects Overpass's public fair-use policy — its free instance
    rate-limits aggressively, and 21 back-to-back requests were observed hitting that limit
    during development.
    """
    from domain.communes import CENTROIDS, COMMUNES

    n_added = 0
    for i, c in enumerate(COMMUNES):
        centroid = CENTROIDS.get(c.id)
        if centroid is None:
            continue
        if i > 0 and delay_s > 0:
            time.sleep(delay_s)
        lat, lon = centroid
        for facility in _fetch_facilities_near(lat, lon):
            fac_uri = TEYVA[f"facility_{facility['osm_id'].replace('/', '_')}"]
            g.add((fac_uri, RDF.type, TEYVA.CriticalFacility))
            g.add((fac_uri, TEYVA.nombre, Literal(facility["name"], datatype=XSD.string)))
            g.add((_territory_uri(c.id), TEYVA.exposes, fac_uri))
            n_added += 1
    return n_added


def node_count(g: Graph) -> int:
    return len({s for s, _, _ in g if isinstance(s, URIRef)})


def edge_count(g: Graph) -> int:
    return len(g)


QUERIES_DIR = __import__("pathlib").Path(__file__).resolve().parent / "queries"


def run_named_query(g: Graph, name: str, *, commune_id: str) -> list[dict[str, str]]:
    """Runs one of the `.sparql` files in `kg/queries/` against `g`, binding `?commune_id`.

    `domain/rules/catalog.py` rules that need a spatial predicate (e.g. "does this territory
    share a stream with a territory that had a recent event") call this instead of embedding
    SPARQL inline — one place to audit every query the reasoner can issue.
    """
    query_text = (QUERIES_DIR / f"{name}.sparql").read_text(encoding="utf-8")
    results = g.query(
        query_text, initBindings={"commune_id": Literal(commune_id, datatype=XSD.string)}
    )
    return [{str(k): str(v) for k, v in row.asdict().items()} for row in results]


if __name__ == "__main__":
    graph = build_static_graph()
    print(f"territories: {node_count(graph)}, triples: {edge_count(graph)}")
