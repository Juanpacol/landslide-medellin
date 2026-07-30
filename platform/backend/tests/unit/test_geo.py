"""Tests puros de domain/geo.py. Sin BD, sin red — solo matemática."""

from __future__ import annotations

import math

import pytest

from domain.geo import (
    EARTH_RADIUS_KM,
    MIN_ACTIVE_PRECIP_MM,
    MIN_STATIONS_FOR_IDW,
    distance_km,
    haversine_km,
    idw_precip,
)


class TestHaversineKm:
    def test_same_point_is_zero_distance(self):
        assert haversine_km(-75.5, 6.25, -75.5, 6.25) == pytest.approx(0.0, abs=1e-9)

    def test_known_medellin_distance_is_plausible(self):
        # El Poblado centroid to San Antonio de Prado centroid, roughly ~14km apart.
        d = haversine_km(-75.554248, 6.197583, -75.669300, 6.196107)
        assert 10.0 < d < 20.0

    def test_antipodal_points_is_half_circumference(self):
        d = haversine_km(0.0, 0.0, 180.0, 0.0)
        assert d == pytest.approx(math.pi * EARTH_RADIUS_KM, rel=1e-6)

    def test_distance_is_symmetric(self):
        d1 = haversine_km(-75.5, 6.2, -75.6, 6.3)
        d2 = haversine_km(-75.6, 6.3, -75.5, 6.2)
        assert d1 == pytest.approx(d2)

    def test_swapped_lat_lon_gives_wrong_but_no_crash(self):
        # Documented failure mode: swapping args doesn't raise, just gives a
        # different (wrong) plausible number.
        correct = haversine_km(-75.5, 6.2, -75.6, 6.3)
        swapped = haversine_km(6.2, -75.5, 6.3, -75.6)
        assert isinstance(swapped, float)
        assert swapped != pytest.approx(correct)

    def test_negative_coordinates_do_not_raise(self):
        d = haversine_km(-75.0, -6.0, -76.0, -7.0)
        assert d > 0

    def test_extreme_latitude_clamped_domain_does_not_raise(self):
        # a can theoretically exceed 1.0 due to floating-point error at poles;
        # the min(1.0, ...) clamp inside asin must prevent a math domain error.
        d = haversine_km(0.0, 90.0, 180.0, -90.0)
        assert isinstance(d, float)


class TestDistanceKm:
    def test_matches_haversine_with_correct_argument_order(self):
        lat1, lon1, lat2, lon2 = 6.2, -75.5, 6.3, -75.6
        assert distance_km(lat1=lat1, lon1=lon1, lat2=lat2, lon2=lon2) == pytest.approx(
            haversine_km(lon1, lat1, lon2, lat2)
        )

    def test_is_keyword_only(self):
        with pytest.raises(TypeError):
            distance_km(6.2, -75.5, 6.3, -75.6)  # type: ignore[misc]

    def test_zero_distance_for_identical_points(self):
        assert distance_km(lat1=6.2, lon1=-75.5, lat2=6.2, lon2=-75.5) == pytest.approx(
            0.0, abs=1e-9
        )


class TestIdwPrecip:
    CENTROID = (6.2, -75.5)

    def test_none_when_fewer_than_min_stations_active(self):
        assert MIN_STATIONS_FOR_IDW == 2
        points = [(6.2, -75.5, 5.0)]
        result = idw_precip(points, centroid_lat=self.CENTROID[0], centroid_lon=self.CENTROID[1])
        assert result is None

    def test_none_when_all_stations_below_active_threshold(self):
        points = [
            (6.2, -75.5, 0.0),
            (6.21, -75.51, MIN_ACTIVE_PRECIP_MM),
        ]
        result = idw_precip(points, centroid_lat=self.CENTROID[0], centroid_lon=self.CENTROID[1])
        assert result is None

    def test_none_when_zero_stations_reported(self):
        result = idw_precip([], centroid_lat=self.CENTROID[0], centroid_lon=self.CENTROID[1])
        assert result is None

    def test_inactive_stations_are_excluded_not_averaged_in(self):
        # A commune with 3 dry stations (0.0mm) and 2 wet ones should reflect the wet ones,
        # not get diluted toward zero by the dry majority — the exact bug audit finding 2
        # documented (180/228 zeroed stations dragging the mean to 0.003mm).
        points = [
            (6.2, -75.5, 0.0),
            (6.2, -75.5, 0.0),
            (6.2, -75.5, 0.0),
            (6.2, -75.5, 10.0),
            (6.2, -75.5, 10.0),
        ]
        result = idw_precip(points, centroid_lat=self.CENTROID[0], centroid_lon=self.CENTROID[1])
        assert result == pytest.approx(10.0)

    def test_coincident_station_returns_its_own_value(self):
        points = [(6.2, -75.5, 7.5), (6.5, -75.9, 2.0)]
        result = idw_precip(points, centroid_lat=6.2, centroid_lon=-75.5)
        assert result == pytest.approx(7.5)

    def test_closer_station_weighted_more_than_farther_one(self):
        near = (6.201, -75.501, 20.0)  # ~0.15km from centroid
        far = (6.5, -75.9, 2.0)  # tens of km away
        result = idw_precip(
            [near, far], centroid_lat=self.CENTROID[0], centroid_lon=self.CENTROID[1]
        )
        assert result is not None
        assert result > 15.0  # dominated by the near station, not a flat (20+2)/2=11 average

    def test_equidistant_stations_average_evenly(self):
        # Two stations symmetric around the centroid on the same latitude get equal weight.
        points = [
            (6.2, -75.51, 4.0),
            (6.2, -75.49, 8.0),
        ]
        result = idw_precip(points, centroid_lat=6.2, centroid_lon=-75.5)
        assert result == pytest.approx(6.0, rel=1e-6)
