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

from owlready2 import DataProperty, FunctionalProperty, ObjectProperty, Thing, get_ontology

from domain.communes import COMMUNES

ONTOLOGY_IRI = "http://teyva.local/onto.owl"
ONTOLOGY_PATH = Path(__file__).resolve().parents[4] / "ontology" / "teyva.owl"


def build_ontology():
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

        # ── A-Box: one individual per commune/corregimiento, from domain/communes.py ──
        for c in COMMUNES:
            cls = Corregimiento if c.tipo == "corregimiento" else Commune
            individual = cls(f"territory_{c.id}")
            individual.canonical_id = c.id
            individual.official_code = c.official_code
            individual.nombre = c.nombre
            individual.is_ladera = c.is_ladera

    return onto


def save(onto=None, path: Path = ONTOLOGY_PATH) -> Path:
    onto = onto or build_ontology()
    path.parent.mkdir(parents=True, exist_ok=True)
    onto.save(file=str(path), format="rdfxml")
    return path


if __name__ == "__main__":
    out = save()
    print(f"Wrote {out}")
