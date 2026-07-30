"""Tests puros de domain/communes.py — territory single-source-of-truth.

`find_communes_in_text` already has dedicated regression coverage in
`test_find_communes_in_text.py`; this file covers the rest of the module:
`canonical_id`, `centroid`, `display_name`, `resolve_commune_id`, and the
static data tables (`COMMUNES`, `BY_ID`, `BY_OFFICIAL_CODE`, `CENTROIDS`).
"""

from __future__ import annotations

import pytest

from domain.communes import (
    BY_ID,
    BY_OFFICIAL_CODE,
    CENTROIDS,
    COMMUNES,
    VALLEY_CENTROID,
    canonical_id,
    centroid,
    display_name,
    resolve_commune_id,
)


class TestStaticTables:
    def test_21_communes_total(self):
        assert len(COMMUNES) == 21

    def test_16_comunas_5_corregimientos(self):
        comunas = [c for c in COMMUNES if c.tipo == "comuna"]
        corregimientos = [c for c in COMMUNES if c.tipo == "corregimiento"]
        assert len(comunas) == 16
        assert len(corregimientos) == 5

    def test_ids_are_1_through_21_with_no_gaps(self):
        ids = sorted(int(c.id) for c in COMMUNES)
        assert ids == list(range(1, 22))

    def test_by_id_and_by_official_code_cover_all_communes(self):
        assert len(BY_ID) == 21
        assert len(BY_OFFICIAL_CODE) == 21

    def test_every_commune_has_a_centroid(self):
        for c in COMMUNES:
            assert c.id in CENTROIDS

    def test_valley_centroid_is_not_any_commune_centroid(self):
        assert VALLEY_CENTROID not in CENTROIDS.values()


class TestCanonicalId:
    def test_canonical_id_passthrough(self):
        assert canonical_id("18") == "18"

    def test_official_corregimiento_code_translated(self):
        assert canonical_id("60") == "18"

    def test_zero_padded_comuna_code_stripped(self):
        assert canonical_id("05") == "5"

    def test_extracts_digits_from_mixed_string(self):
        assert canonical_id("m-7") == "7"

    def test_none_returns_none(self):
        assert canonical_id(None) is None

    def test_no_digits_returns_none(self):
        assert canonical_id("no-digits-here") is None

    def test_int_input(self):
        assert canonical_id(18) == "18"

    def test_unknown_numeric_id_returned_normalized_not_none(self):
        assert canonical_id("999") == "999"

    def test_empty_string_returns_none(self):
        assert canonical_id("") is None


class TestCentroid:
    def test_known_commune_returns_tuple(self):
        result = centroid("1")
        assert result == CENTROIDS["1"]

    def test_accepts_official_code(self):
        assert centroid("50") == CENTROIDS["17"]  # Palmitas

    def test_unknown_id_returns_none(self):
        assert centroid("does-not-exist") is None

    def test_none_returns_none(self):
        assert centroid(None) is None


class TestDisplayName:
    def test_known_commune_name(self):
        assert display_name("14") == "El Poblado"

    def test_official_code_resolves_name(self):
        assert display_name("90") == "Santa Elena"

    def test_unknown_id_falls_back_to_generic_label(self):
        assert display_name("999") == "Comuna 999"

    def test_none_returns_sin_datos(self):
        assert display_name(None) == "Sin datos"


class TestResolveCommuneId:
    def test_numeric_string_resolves_via_canonical_id(self):
        assert resolve_commune_id("18") == "18"

    def test_exact_name_match(self):
        assert resolve_commune_id("El Poblado") == "14"

    def test_name_without_accent_or_case(self):
        assert resolve_commune_id("poblado") == "14"

    def test_alias_resolves(self):
        assert resolve_commune_id("Laureles") == "11"

    def test_unknown_name_returns_none(self):
        assert resolve_commune_id("Not A Real Place") is None

    def test_empty_string_returns_none(self):
        assert resolve_commune_id("") is None

    def test_none_like_input_returns_none(self):
        assert resolve_commune_id(None) is None  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "alias,expected_id",
        [
            ("doce de octubre", "6"),
            ("la america", "12"),
            ("laureles-estadio", "11"),
            ("san cristobal", "18"),
            ("candelaria", "10"),
            ("centro", "10"),
            ("villa hermosa", "8"),
            ("belen", "16"),
        ],
    )
    def test_extra_aliases(self, alias, expected_id):
        assert resolve_commune_id(alias) == expected_id
