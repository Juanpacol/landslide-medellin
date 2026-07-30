"""Tests for kg/export_cypher.py — Neo4j Cypher export, visualization-only (ADR-0001).
No network, no Neo4j instance: verifies the generated Cypher text is well-formed and
references real data from build_static_graph(), not that it actually imports into Neo4j.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rdflib")

from domain.communes import COMMUNES  # noqa: E402
from kg.build import build_static_graph  # noqa: E402
from kg.export_cypher import graph_to_cypher  # noqa: E402


def test_one_merge_statement_per_commune():
    g = build_static_graph()
    cypher = graph_to_cypher(g)
    for c in COMMUNES:
        assert f"canonical_id: '{c.id}'" in cypher


def test_output_is_only_merge_and_match_statements():
    g = build_static_graph()
    cypher = graph_to_cypher(g)
    lines = [line for line in cypher.splitlines() if line.strip()]
    assert lines  # non-empty
    for line in lines:
        assert line.startswith("MERGE") or line.startswith("MATCH")


def test_adjacency_edges_are_present():
    g = build_static_graph()
    cypher = graph_to_cypher(g)
    assert "MERGE (a)-[:ADJACENT_TO]->(b)" in cypher


def test_every_statement_is_terminated():
    g = build_static_graph()
    cypher = graph_to_cypher(g)
    for line in cypher.splitlines():
        if line.strip():
            assert line.rstrip().endswith(";")


def test_single_quotes_in_names_are_escaped():
    # "La América" has an accent, not a quote, but this guards the _escape() path itself
    # rather than relying on real data happening to contain one.
    from kg.export_cypher import _escape

    assert _escape("O'Brien") == "O\\'Brien"
