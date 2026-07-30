"""Builds `ontology/teyva.owl` from scratch using owlready2's Python API, then generates the 21
territory individuals directly from `domain/communes.py::COMMUNES` — never hand-typed, per
specs/001-ontology/spec.md criterion 2 ("a second commune list is a bug by definition",
domain/communes.py's own docstring).

Run manually when the T-Box or the commune list changes:

    cd platform/backend && export PYTHONPATH=.
    python -m infrastructure.ontology.build

This is I/O (writes a file) and imports owlready2, so it lives in `infrastructure/`, never in
`domain/` — same layering rule as every other external-facing client in this package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from owlready2 import DataProperty, FunctionalProperty, ObjectProperty, Thing, get_ontology

from domain.communes import COMMUNES
from domain.rules.catalog import CATALOG

ONTOLOGY_IRI = "http://teyva.local/onto.owl"
ONTOLOGY_PATH = Path(__file__).resolve().parents[4] / "ontology" / "teyva.owl"


def build_ontology() -> Any:
    """Builds the ontology (T-Box + A-Box) in memory from `domain/communes.py` and
    `domain/rules/catalog.py`; does not write it to disk."""
    onto = get_ontology(ONTOLOGY_IRI)

    with onto:
        # ── T-Box: classes ──────────────────────────────────────────────────
        class Territory(Thing):
            """A comuna or corregimiento of Medellín — domain/communes.py is the source of
            individuals for this class."""

        class Commune(Territory):
            pass

        class Corregimiento(Territory):
            pass

        class TerrainFeature(Thing):
            pass

        class Slope(TerrainFeature):
            pass

        class TWI(TerrainFeature):
            pass

        class NDVI(TerrainFeature):
            pass

        class SoilType(TerrainFeature):
            pass

        class Elevation(TerrainFeature):
            pass

        class HydroFeature(Thing):
            pass

        class Stream(HydroFeature):
            pass

        class Trigger(Thing):
            pass

        class RainfallEvent(Trigger):
            pass

        class SeismicEvent(Trigger):
            pass

        class Exposure(Thing):
            pass

        class Dwelling(Exposure):
            pass

        class CriticalFacility(Exposure):
            pass

        class Hospital(CriticalFacility):
            pass

        class School(CriticalFacility):
            pass

        class Shelter(CriticalFacility):
            pass

        class LandslideEvent(Thing):
            pass

        class HazardAssessment(Thing):
            pass

        class DataQualityFlag(Thing):
            pass

        class SymbolicRule(Thing):
            """A formal-specification stub for one entry in
            `domain/rules/catalog.py::CATALOG` — the executable rule engine (ADR-0002),
            not this ontology. Not an executable SWRL `Imp`: the ontology's
            per-feature class model (slope on `Slope`, not `Territory` directly)
            doesn't map cleanly onto flat SWRL rule bodies without a larger
            ontology redesign than this spec's scope. `swrl_sketch` is a
            human-readable SWRL-flavored condition→effect string for traceability,
            not something owlready2 or a reasoner executes.

            Generated from `domain.rules.catalog.CATALOG`, never hand-typed — the
            same "single source, never a second list" discipline as the 21
            territory individuals below. `infrastructure/ontology/loader.py`
            exposes `rule_ids()`, and `tests/test_ontology.py` asserts this set
            equals `{r.id for r in CATALOG}`, so the ontology and the rule engine
            cannot silently drift apart.
            """

        # ── T-Box: object properties ────────────────────────────────────────
        class locatedIn(ObjectProperty):
            domain = [Thing]
            range = [Territory]

        class adjacentTo(ObjectProperty):
            domain = [Territory]
            range = [Territory]
            symmetric = True

        class drainedBy(ObjectProperty):
            domain = [Territory]
            range = [Stream]

        class hasTerrainFeature(ObjectProperty):
            domain = [Territory]
            range = [TerrainFeature]

        class exposes(ObjectProperty):
            domain = [Territory]
            range = [Exposure]

        class triggeredBy(ObjectProperty):
            domain = [HazardAssessment]
            range = [Trigger]

        class hasHistoricalEvent(ObjectProperty):
            domain = [Territory]
            range = [LandslideEvent]

        class assessedBy(ObjectProperty):
            domain = [Territory]
            range = [HazardAssessment]

        # ── T-Box: datatype properties (mirror DB column names exactly) ─────
        class canonical_id(DataProperty, FunctionalProperty):
            domain = [Territory]
            range = [str]

        class official_code(DataProperty, FunctionalProperty):
            domain = [Territory]
            range = [str]

        class nombre(DataProperty, FunctionalProperty):
            domain = [Territory]
            range = [str]

        class is_ladera(DataProperty, FunctionalProperty):
            domain = [Territory]
            range = [bool]

        class slope_p90_deg(DataProperty, FunctionalProperty):
            domain = [Slope]
            range = [float]

        class twi_p90(DataProperty, FunctionalProperty):
            domain = [TWI]
            range = [float]

        class ndvi_min(DataProperty, FunctionalProperty):
            domain = [NDVI]
            range = [float]

        class hazard_fraction(DataProperty, FunctionalProperty):
            domain = [HazardAssessment]
            range = [float]

        class precip_mm(DataProperty, FunctionalProperty):
            domain = [RainfallEvent]
            range = [float]

        class magnitude(DataProperty, FunctionalProperty):
            domain = [SeismicEvent]
            range = [float]

        class rule_id(DataProperty, FunctionalProperty):
            """Matches `domain.rules.engine.Rule.id` exactly (e.g. "R-GEO-01")."""

            domain = [SymbolicRule]
            range = [str]

        class priority(DataProperty, FunctionalProperty):
            domain = [SymbolicRule]
            range = [int]

        class provenance(DataProperty, FunctionalProperty):
            domain = [SymbolicRule]
            range = [str]

        class swrl_sketch(DataProperty, FunctionalProperty):
            """Human-readable, non-executable condition→effect sketch — see
            `SymbolicRule`'s docstring for why this isn't a real SWRL `Imp`."""

            domain = [SymbolicRule]
            range = [str]

        # ── A-Box: one individual per commune/corregimiento, from domain/communes.py ──
        for c in COMMUNES:
            cls = Corregimiento if c.tipo == "corregimiento" else Commune
            individual = cls(f"territory_{c.id}")
            individual.canonical_id = c.id
            individual.official_code = c.official_code
            individual.nombre = c.nombre
            individual.is_ladera = c.is_ladera

        # ── A-Box: one SymbolicRule individual per domain/rules/catalog.py entry ──
        for rule in CATALOG:
            slug = rule.id.replace("-", "_").lower()
            rule_ind = SymbolicRule(f"rule_{slug}")
            rule_ind.rule_id = rule.id
            rule_ind.priority = rule.priority
            rule_ind.provenance = rule.provenance
            rule_ind.swrl_sketch = f"{rule.description} => {type(rule.effect).__name__}"

    return onto


def save(onto: Any = None, path: Path = ONTOLOGY_PATH) -> Path:
    """Builds (if needed) and writes the ontology to `path` as RDF/XML."""
    onto = onto or build_ontology()
    path.parent.mkdir(parents=True, exist_ok=True)
    onto.save(file=str(path), format="rdfxml")
    return path


if __name__ == "__main__":
    out = save()
    print(f"Wrote {out}")
