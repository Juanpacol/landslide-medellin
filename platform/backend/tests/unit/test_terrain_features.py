"""Tests for scraper/terrain_features.py's pure helpers — no network, no DB.

specs/006-neural-estimators/tasks.md: the terrain-ingestion gap. These tests
cover the finite-difference slope math and the sampling geometry; the actual
DEM API call is exercised only by hand (`python -m scraper.terrain_features`),
not in CI.
"""

from __future__ import annotations

import math

from scraper.terrain_features import (
    SAMPLE_OFFSET_M,
    _centroid_lonlat,
    _offset_points,
    _slope_deg_from_elevations,
)


def test_offset_points_returns_five_directions():
    points = _offset_points(6.25, -75.57, SAMPLE_OFFSET_M)
    assert set(points.keys()) == {"center", "N", "S", "E", "W"}
    assert points["center"] == (6.25, -75.57)


def test_offset_points_north_is_higher_latitude():
    points = _offset_points(6.25, -75.57, SAMPLE_OFFSET_M)
    assert points["N"][0] > points["center"][0] > points["S"][0]
    assert points["E"][1] > points["center"][1] > points["W"][1]


def test_slope_zero_on_flat_terrain():
    flat = {"center": 100.0, "N": 100.0, "S": 100.0, "E": 100.0, "W": 100.0}
    assert _slope_deg_from_elevations(flat, SAMPLE_OFFSET_M) == 0.0


def test_slope_positive_on_a_ramp():
    # A steady 45-degree ramp along the N-S axis: dz/dy = 1 over the offset.
    ramp = {
        "center": 0.0,
        "N": SAMPLE_OFFSET_M,
        "S": -SAMPLE_OFFSET_M,
        "E": 0.0,
        "W": 0.0,
    }
    slope = _slope_deg_from_elevations(ramp, SAMPLE_OFFSET_M)
    assert slope is not None
    assert math.isclose(slope, 45.0, abs_tol=0.1)


def test_slope_none_when_any_neighbor_missing():
    partial = {"center": 100.0, "N": 105.0, "S": None, "E": 100.0, "W": 100.0}
    assert _slope_deg_from_elevations(partial, SAMPLE_OFFSET_M) is None


def test_centroid_polygon():
    geometry = {
        "type": "Polygon",
        "coordinates": [[[-75.6, 6.2], [-75.6, 6.3], [-75.5, 6.3], [-75.5, 6.2], [-75.6, 6.2]]],
    }
    centroid = _centroid_lonlat(geometry)
    assert centroid is not None
    lon, lat = centroid
    assert -75.6 <= lon <= -75.5
    assert 6.2 <= lat <= 6.3


def test_centroid_unknown_geometry_type_returns_none():
    assert _centroid_lonlat({"type": "Point", "coordinates": [-75.5, 6.2]}) is None
