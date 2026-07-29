"""Tests for kg/build.py — the knowledge-graph skeleton (specs/005-knowledge-graph/).

Scope: the static, DB-free path only (territory nodes + centroid-proximity adjacency). Full
Postgres A-Box population is not implemented yet — see specs/005-knowledge-graph/tasks.md.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rdflib")

from domain.communes import COMMUNES  # noqa: E402
from kg.build import ADJACENCY_K, build_static_graph, node_count, run_named_query  # noqa: E402


def test_node_count_matches_commune_count():
    g = build_static_graph()
    assert node_count(g) == len(COMMUNES)


def test_no_orphan_territory_every_commune_has_at_least_one_adjacency():
    g = build_static_graph()
    for c in COMMUNES:
        result = run_named_query(g, "upslope_neighbours", commune_id=c.id)
        assert len(result) >= 1, f"commune {c.id} has no adjacency edges"


def test_adjacency_is_bounded_by_k():
    g = build_static_graph()
    result = run_named_query(g, "upslope_neighbours", commune_id="8")
    assert len(result) <= ADJACENCY_K


def test_named_query_returns_typed_results_with_names():
    g = build_static_graph()
    result = run_named_query(g, "upslope_neighbours", commune_id="1")
    assert all("nombre" in row for row in result)
    assert all(isinstance(row["nombre"], str) and row["nombre"] for row in result)
