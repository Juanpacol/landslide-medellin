"""Knowledge graph A-Box builder — populates an `rdflib.Graph` with territory individuals and
`adjacentTo` edges, queryable via SPARQL. `domain/rules/catalog.py` rules that need spatial
predicates (e.g. a future "upslope neighbour" rule) call `run_query()`, not the DB directly —
this is runtime infrastructure, not a visualization demo (specs/005-knowledge-graph/spec.md).

Scope note vs. the original spec: full A-Box population from Postgres (barrio_terrain,
barrio_hazard, safe_zones, seismic_events, non-synthetic landslide_events) and polygon-based
adjacency via shapely are NOT implemented here — that needs an AsyncSession and the barrio
polygon file, both bigger asynchronous integration work. What IS implemented: territory nodes
(reusing infrastructure/ontology/loader.py, so there's exactly one definition of "the 21
territories") and a centroid-proximity approximation of `adjacentTo`, declared as an
approximation, not the real polygon-adjacency the full spec calls for
(specs/005-knowledge-graph/tasks.md tracks the rest).
"""

from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

TEYVA = Namespace("http://teyva.local/onto.owl#")

# How many nearest neighbours count as "adjacent" — a centroid-distance approximation of true
# polygon adjacency (which needs the barrio/comuna polygon file, not yet wired in).
ADJACENCY_K = 3


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


def build_static_graph() -> Graph:
    """Territories + centroid-proximity adjacency. No DB access — pulls from
    `domain/communes.py` directly, so it can build (and be tested) without a database."""
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

    for cid, centroid in CENTROIDS.items():
        distances = sorted(
            ((other_id, _haversine_km(centroid, other_centroid)) for other_id, other_centroid in CENTROIDS.items() if other_id != cid),
            key=lambda x: x[1],
        )
        for other_id, _dist in distances[:ADJACENCY_K]:
            g.add((_territory_uri(cid), TEYVA.adjacentTo, _territory_uri(other_id)))

    return g


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
    results = g.query(query_text, initBindings={"commune_id": Literal(commune_id, datatype=XSD.string)})
    return [{str(k): str(v) for k, v in row.asdict().items()} for row in results]


if __name__ == "__main__":
    graph = build_static_graph()
    print(f"territories: {node_count(graph)}, triples: {edge_count(graph)}")
