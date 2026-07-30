"""Tests for kg/build.py — the knowledge-graph skeleton (specs/005-knowledge-graph/).

Scope: the static, DB-free path only (territory nodes + adjacency: true polygon adjacency for
the 16 urban comunas via kg/polygon_adjacency.py, centroid-proximity fallback for the 5
corregimientos). Full Postgres A-Box population is not implemented yet — see
specs/005-knowledge-graph/tasks.md.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rdflib")

from domain.communes import COMMUNES  # noqa: E402
from kg.build import (  # noqa: E402
    ADJACENCY_K,
    TEYVA,
    add_critical_facilities,
    build_static_graph,
    node_count,
    run_named_query,
)


def test_node_count_matches_commune_count():
    g = build_static_graph()
    assert node_count(g) == len(COMMUNES)


def test_no_orphan_territory_every_commune_has_at_least_one_adjacency():
    g = build_static_graph()
    for c in COMMUNES:
        result = run_named_query(g, "upslope_neighbours", commune_id=c.id)
        assert len(result) >= 1, f"commune {c.id} has no adjacency edges"


def test_corregimiento_adjacency_is_bounded_by_k():
    # Corregimientos (17-21) have no polygon coverage in barrios-medellin.json, so they
    # still use the centroid-proximity fallback, bounded by ADJACENCY_K.
    g = build_static_graph()
    result = run_named_query(g, "upslope_neighbours", commune_id="17")  # Palmitas
    assert len(result) <= ADJACENCY_K


def test_urban_comuna_uses_true_polygon_adjacency_not_capped_at_k():
    # Commune 10 (La Candelaria, downtown) has 10 real polygon neighbors per
    # kg/polygon_adjacency.py — more than ADJACENCY_K=3, proving this isn't the old
    # centroid-proximity fallback for communes the polygon file covers.
    g = build_static_graph()
    result = run_named_query(g, "upslope_neighbours", commune_id="10")
    assert len(result) > ADJACENCY_K


def test_use_polygon_adjacency_false_falls_back_to_centroid_proximity_for_all():
    g = build_static_graph(use_polygon_adjacency=False)
    for cid in ("1", "10", "17"):
        result = run_named_query(g, "upslope_neighbours", commune_id=cid)
        assert len(result) <= ADJACENCY_K


def test_named_query_returns_typed_results_with_names():
    g = build_static_graph()
    result = run_named_query(g, "upslope_neighbours", commune_id="1")
    assert all("nombre" in row for row in result)
    assert all(isinstance(row["nombre"], str) and row["nombre"] for row in result)


def test_shared_stream_query_is_honestly_empty_on_the_static_graph():
    # Hydrography/landslide-event data needs Postgres, which this DB-free build path
    # doesn't have (specs/005-knowledge-graph/tasks.md) — the query must return empty,
    # not error, and definitely not fabricate a result.
    g = build_static_graph()
    result = run_named_query(g, "shared_stream_recent_event", commune_id="1")
    assert result == []


def test_add_critical_facilities_populates_exposed_facilities_query(monkeypatch):
    from rdflib import RDF, Literal
    from rdflib.namespace import XSD

    import kg.build as kg_build

    def _fake_fetch(lat, lon):
        return [{"osm_id": "node/123", "name": "Hospital Test", "amenity": "hospital", "lat": lat, "lon": lon}]

    monkeypatch.setattr(kg_build, "_fetch_facilities_near", _fake_fetch)

    g = build_static_graph()
    n_added = add_critical_facilities(g, delay_s=0)

    assert n_added == len(COMMUNES)  # one fake facility per commune
    result = run_named_query(g, "exposed_facilities", commune_id="1")
    assert len(result) == 1
    assert result[0]["nombre"] == "Hospital Test"

    # Sanity: the facility individual is actually typed as CriticalFacility.
    facility_uri = TEYVA["facility_node_123"]
    assert (facility_uri, RDF.type, TEYVA.CriticalFacility) in g
