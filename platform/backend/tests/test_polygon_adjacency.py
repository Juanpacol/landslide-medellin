"""Tests for kg/polygon_adjacency.py — true polygon-based commune adjacency via shapely,
over the real barrios-medellin.json file (no network, no DB: a static file already in the
repo). specs/005-knowledge-graph/tasks.md's "true polygon-based adjacency" item.
"""

from __future__ import annotations

import pytest

pytest.importorskip("shapely")

from kg.polygon_adjacency import DEFAULT_GEOJSON, commune_union_shapes, polygon_adjacency  # noqa: E402

pytestmark = pytest.mark.skipif(
    not DEFAULT_GEOJSON.exists(), reason="frontend/lib/barrios-medellin.json not found"
)


def test_covers_only_the_16_urban_comunas_not_corregimientos():
    adj = polygon_adjacency()
    # Corregimientos are 17-21 in canonical id; barrios-medellin.json has no polygon data
    # for them (module docstring) — they must NOT appear here.
    assert set(adj.keys()) == {str(i) for i in range(1, 17)}


def test_adjacency_is_symmetric():
    adj = polygon_adjacency()
    for cid, neighbors in adj.items():
        for n in neighbors:
            assert cid in adj[n], f"{cid} lists {n} as neighbor but not vice versa"


def test_no_commune_is_its_own_neighbor():
    adj = polygon_adjacency()
    for cid, neighbors in adj.items():
        assert cid not in neighbors


def test_every_commune_has_at_least_one_real_neighbor():
    # A commune with zero polygon neighbors would suggest a data/geometry problem, not a
    # real isolated territory — Medellín's 16 comunas form one contiguous urban area.
    adj = polygon_adjacency()
    for cid, neighbors in adj.items():
        assert len(neighbors) >= 1, f"commune {cid} has no polygon-adjacent neighbors"


def test_commune_union_shapes_are_valid_geometries():
    shapes = commune_union_shapes()
    for cid, geom in shapes.items():
        assert geom.is_valid, f"commune {cid}'s unioned shape is not a valid geometry"
        assert not geom.is_empty
