"""Optional Neo4j Cypher export of the in-memory `kg.build` graph — for visualization only, per
ADR-0001 ("no Neo4j service, optional Cypher export for visuals"). Not runtime infrastructure:
nothing in the inference path reads this file; a human imports it into Neo4j Desktop/Browser to
look at the graph.

No sync obligation: this is generated from whatever `rdflib.Graph` you pass in, on demand. If
`kg.build`'s territory/adjacency/facility data changes, regenerate — there's no live connection
to keep in sync.

Usage:

    cd platform/backend && export PYTHONPATH=.
    python -m kg.export_cypher --with-facilities > graph.cypher
    # then in Neo4j Browser: paste graph.cypher's contents, or `:play` it via cypher-shell
"""

from __future__ import annotations

import argparse

from rdflib import RDF, Graph, URIRef

from kg.build import TEYVA, add_critical_facilities, build_static_graph


def _local_name(uri: URIRef) -> str:
    """The part after the `#` in a `TEYVA[...]` URI, e.g. `territory_8` from
    `http://teyva.local/onto.owl#territory_8`."""
    return str(uri).rsplit("#", 1)[-1]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _cypher_label(class_uri: URIRef) -> str:
    return _local_name(class_uri)


def graph_to_cypher(g: Graph) -> str:
    """Converts a `kg.build`-shaped RDF graph into a sequence of Cypher `MERGE` statements.

    Two node kinds: `Territory` (`Commune`/`Corregimiento`, keyed by `canonical_id`) and
    `CriticalFacility` (keyed by its local URI name, since facilities have no canonical id).
    Two edge kinds: `ADJACENT_TO` (from `teyva:adjacentTo`) and `EXPOSES` (from `teyva:exposes`).
    `MERGE` (not `CREATE`) makes re-running the same export idempotent in Neo4j.
    """
    lines: list[str] = []

    territories = set(g.subjects(RDF.type, TEYVA.Commune)) | set(
        g.subjects(RDF.type, TEYVA.Corregimiento)
    )
    for uri in sorted(territories, key=_local_name):
        cls = TEYVA.Corregimiento if (uri, RDF.type, TEYVA.Corregimiento) in g else TEYVA.Commune
        canonical_id = next(g.objects(uri, TEYVA.canonical_id), None)
        nombre = next(g.objects(uri, TEYVA.nombre), None)
        is_ladera = next(g.objects(uri, TEYVA.is_ladera), None)
        lines.append(
            f"MERGE (t_{_local_name(uri)}:{_cypher_label(cls)} {{canonical_id: '{_escape(str(canonical_id))}'}}) "
            f"SET t_{_local_name(uri)}.nombre = '{_escape(str(nombre))}', "
            f"t_{_local_name(uri)}.is_ladera = {str(is_ladera).lower() if is_ladera is not None else 'null'};"
        )

    facilities = set(g.subjects(RDF.type, TEYVA.CriticalFacility))
    for uri in sorted(facilities, key=_local_name):
        nombre = next(g.objects(uri, TEYVA.nombre), None)
        lines.append(
            f"MERGE (f_{_local_name(uri)}:CriticalFacility {{osm_ref: '{_escape(_local_name(uri))}'}}) "
            f"SET f_{_local_name(uri)}.nombre = '{_escape(str(nombre))}';"
        )

    for s, o in sorted(
        g.subject_objects(TEYVA.adjacentTo), key=lambda so: (_local_name(so[0]), _local_name(so[1]))
    ):
        lines.append(
            f"MATCH (a {{canonical_id: '{_escape(str(next(g.objects(s, TEYVA.canonical_id), '')))}'}}), "
            f"(b {{canonical_id: '{_escape(str(next(g.objects(o, TEYVA.canonical_id), '')))}'}}) "
            f"MERGE (a)-[:ADJACENT_TO]->(b);"
        )

    for s, o in sorted(
        g.subject_objects(TEYVA.exposes), key=lambda so: (_local_name(so[0]), _local_name(so[1]))
    ):
        lines.append(
            f"MATCH (t {{canonical_id: '{_escape(str(next(g.objects(s, TEYVA.canonical_id), '')))}'}}), "
            f"(f:CriticalFacility {{osm_ref: '{_escape(_local_name(o))}'}}) "
            f"MERGE (t)-[:EXPOSES]->(f);"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-facilities",
        action="store_true",
        help="Also fetch critical facilities from Overpass (network call, ~21 requests, ~1/sec)",
    )
    args = parser.parse_args()

    g = build_static_graph()
    if args.with_facilities:
        add_critical_facilities(g)

    print(graph_to_cypher(g), end="")


if __name__ == "__main__":
    main()
