"""Cached runtime loader for `ontology/teyva.owl`. `domain/` never imports owlready2 — this is
I/O (reads a file, holds it in a process-level cache), so it lives in `infrastructure/`, same as
`arcgis_client.py`/`llm_client.py` for external systems.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

ONTOLOGY_PATH = Path(__file__).resolve().parents[4] / "ontology" / "teyva.owl"


@lru_cache(maxsize=1)
def _load() -> Any:
    """Loads and process-caches the ontology (owlready2 `Ontology`)."""
    from owlready2 import get_ontology

    onto = get_ontology(f"file://{ONTOLOGY_PATH}").load()
    return onto


def ontology_version() -> str:
    """A short hash of the ontology file's contents — changes whenever the T-Box or A-Box
    changes, without needing a manually bumped version number that can go stale."""
    digest = hashlib.sha256(ONTOLOGY_PATH.read_bytes()).hexdigest()
    return digest[:12]


def individuals_for_commune(commune_id: str) -> dict[str, Any] | None:
    """The ontology individual for one commune (by canonical id), as a plain dict — callers
    outside `infrastructure/` should never touch owlready2 objects directly."""
    onto = _load()
    name = f"territory_{commune_id}"
    individual = onto.search_one(iri=f"*{name}")
    if individual is None:
        return None
    return {
        "name": individual.name,
        "canonical_id": individual.canonical_id,
        "official_code": individual.official_code,
        "nombre": individual.nombre,
        "is_ladera": individual.is_ladera,
        "types": [c.name for c in individual.is_a],
    }


def all_territory_individuals() -> list[dict[str, Any]]:
    """The ontology individual for every commune that has one, as plain dicts."""
    from domain.communes import COMMUNES

    out = []
    for c in COMMUNES:
        info = individuals_for_commune(c.id)
        if info is not None:
            out.append(info)
    return out


def rule_ids() -> frozenset[str]:
    """`rule_id` of every `SymbolicRule` individual in the ontology — the SWRL-sketch side of
    the drift check `tests/test_ontology.py` runs against
    `domain.rules.catalog.CATALOG`'s ids (specs/001-ontology/spec.md criterion 4)."""
    onto = _load()
    symbolic_rule_cls = onto.search_one(iri="*SymbolicRule")
    if symbolic_rule_cls is None:
        return frozenset()
    return frozenset(ind.rule_id for ind in symbolic_rule_cls.instances() if ind.rule_id)
