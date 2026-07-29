"""Tests for infrastructure/ontology/loader.py — specs/001-ontology/spec.md acceptance criteria
2 (every commune has an individual, generated from domain/communes.py) and 5
(ontology_version()/individuals_for_commune()).

Requires owlready2 (added to requirements.txt for this spec) and the built ontology file at
ontology/teyva.owl — regenerate with `python -m infrastructure.ontology.build` if
domain/communes.py changes.
"""

from __future__ import annotations

import pytest

pytest.importorskip("owlready2")

from domain.communes import COMMUNES  # noqa: E402
from infrastructure.ontology.loader import (  # noqa: E402
    ONTOLOGY_PATH,
    all_territory_individuals,
    individuals_for_commune,
    ontology_version,
)


@pytest.mark.skipif(not ONTOLOGY_PATH.exists(), reason="ontology/teyva.owl not built")
class TestOntology:
    def test_ontology_version_is_stable_hash(self):
        v1 = ontology_version()
        v2 = ontology_version()
        assert v1 == v2
        assert len(v1) == 12

    def test_every_commune_has_an_individual(self):
        for c in COMMUNES:
            info = individuals_for_commune(c.id)
            assert info is not None, f"missing OWL individual for commune {c.id}"
            assert info["canonical_id"] == c.id
            assert info["nombre"] == c.nombre
            assert info["is_ladera"] == c.is_ladera

    def test_corregimientos_use_official_code_not_canonical_id(self):
        # Regression guard for the exact bug class domain/communes.py's docstring warns about:
        # official code ("50".."90") must never leak into canonical-id fields.
        info = individuals_for_commune("18")  # San Cristóbal
        assert info["canonical_id"] == "18"
        assert info["official_code"] == "60"

    def test_all_territory_individuals_matches_commune_count(self):
        assert len(all_territory_individuals()) == len(COMMUNES)

    def test_unknown_commune_returns_none(self):
        assert individuals_for_commune("999") is None
