"""The geotechnical/expert rule catalog. Thresholds are imported, never redeclared — a second
set of magic numbers next to `domain/susceptibility.py` and `domain/risk_rules.py` would be
exactly the kind of drift `specs/002-rule-engine/spec.md` acceptance criterion 4 forbids.

Each `Rule.provenance` is a citation or expert-judgment note; `specs/007-experimental-eval/`'s
rule table is meant to be generated from this file, not hand-maintained separately.
"""

from __future__ import annotations

from domain.risk_rules import RISK_ALTO
from domain.rules.engine import Escalate, RaisePriority, Rule, SetFloor, Veto
from domain.rules.facts import TerritorySnapshot
from domain.susceptibility import NDVI_BARE, SLOPE_MAX_DEG, TWI_MAX

# Same 120mm/24h threshold used as the illustrative geotechnical example in the project brief;
# expressed here over 72h (`precip_72h_mm`) because that's the window TEYVA's trigger already
# aggregates (`domain/susceptibility.py::trigger_breakdown`'s antecedent window).
HEAVY_RAIN_72H_MM = 120.0
HIGH_SWI_PCT = 80.0
HIGH_ANTECEDENT_MM = 80.0
MODERATE_SLOPE_DEG = 25.0
NDVI_SLOPE_DEG = 30.0
HISTORICAL_PROXIMITY_EVENTS = 1.0
CRITICAL_FACILITY_RADIUS_M = 200.0
SEISMIC_HIGH_INTENSITY = 20.0
MODERATE_SWI_PCT = 60.0


def _r_geo_01(s: TerritorySnapshot) -> bool | None:
    if s.slope_p90_deg is None or s.precip_72h_mm is None:
        return None
    return s.slope_p90_deg > SLOPE_MAX_DEG - 10 and s.precip_72h_mm > HEAVY_RAIN_72H_MM


R_GEO_01 = Rule(
    id="R-GEO-01",
    description="Steep slope (>35°) with heavy 72h rain (>120mm) floors risk at 'alto'.",
    priority=100,
    condition=_r_geo_01,
    effect=SetFloor(level=RISK_ALTO),
    provenance="Standard geotechnical trigger threshold; slope bound matches "
    "domain/susceptibility.py::SLOPE_MAX_DEG saturation point.",
)


def _r_geo_02(s: TerritorySnapshot) -> bool | None:
    if s.slope_p90_deg is None or s.swi_pct is None:
        return None
    return s.slope_p90_deg > MODERATE_SLOPE_DEG and s.swi_pct > HIGH_SWI_PCT


R_GEO_02 = Rule(
    id="R-GEO-02",
    description="Moderate slope (>25°) with saturated soil (SWI>80%) escalates one level.",
    priority=80,
    condition=_r_geo_02,
    effect=Escalate(steps=1),
    provenance="Saturated soil reduces shear strength on moderate slopes; expert judgment "
    "consistent with domain/susceptibility.py's SWI-as-trigger design.",
)


def _r_geo_03(s: TerritorySnapshot) -> bool | None:
    if s.twi_p90 is None or s.antecedent_mm is None:
        return None
    return s.twi_p90 > TWI_MAX - 3 and s.antecedent_mm > HIGH_ANTECEDENT_MM


R_GEO_03 = Rule(
    id="R-GEO-03",
    description="High topographic wetness (water convergence) with high antecedent rain escalates one level.",
    priority=70,
    condition=_r_geo_03,
    effect=Escalate(steps=1),
    provenance="TWI identifies flow-convergence zones (domain/susceptibility.py::TWI_MAX); "
    "combined with antecedent moisture this is a classic saturation-front indicator.",
)


def _r_geo_04(s: TerritorySnapshot) -> bool | None:
    if s.ndvi_min is None or s.slope_p90_deg is None:
        return None
    return s.ndvi_min < NDVI_BARE and s.slope_p90_deg > NDVI_SLOPE_DEG


R_GEO_04 = Rule(
    id="R-GEO-04",
    description="Bare soil (low NDVI) on a steep slope escalates one level.",
    priority=60,
    condition=_r_geo_04,
    effect=Escalate(steps=1),
    provenance="Root cohesion loss on bare, steep terrain; NDVI_BARE threshold shared with "
    "domain/susceptibility.py::normalize_ndvi.",
)


def _r_hist_01(s: TerritorySnapshot) -> bool | None:
    if s.prior_event_count is None:
        return None
    return s.prior_event_count >= HISTORICAL_PROXIMITY_EVENTS


R_HIST_01 = Rule(
    id="R-HIST-01",
    description="At least one historical landslide nearby raises operational priority.",
    priority=50,
    condition=_r_hist_01,
    effect=RaisePriority(to="elevated"),
    provenance="'Dangerous zones repeat' — same rationale as domain/susceptibility.py's "
    "W_PRIOR component, applied here as a priority signal rather than a score input.",
)


def _r_expo_01(s: TerritorySnapshot) -> bool | None:
    if s.nearest_critical_facility_m is None:
        return None
    return s.nearest_critical_facility_m <= CRITICAL_FACILITY_RADIUS_M


R_EXPO_01 = Rule(
    id="R-EXPO-01",
    description="A hospital or school within 200m raises priority to maximum.",
    priority=90,
    condition=_r_expo_01,
    effect=RaisePriority(to="max"),
    provenance="Consequence-weighted prioritization: equal hazard, higher exposure cost. "
    "Data source: SPEC-005's extended Overpass query for amenity=hospital|clinic|school.",
)


def _r_seis_01(s: TerritorySnapshot) -> bool | None:
    if s.seismic_intensity is None or s.swi_pct is None:
        return None
    return s.seismic_intensity > SEISMIC_HIGH_INTENSITY and s.swi_pct > MODERATE_SWI_PCT


R_SEIS_01 = Rule(
    id="R-SEIS-01",
    description="High seismic intensity over moderately saturated soil escalates one level.",
    priority=65,
    condition=_r_seis_01,
    effect=Escalate(steps=1),
    provenance="A quake on saturated soil moves a slope far more readily than on dry soil; "
    "matches domain/susceptibility.py::trigger_breakdown's 'seismic modulates, doesn't "
    "trigger alone' design.",
)


def _r_qual_01(s: TerritorySnapshot) -> bool | None:
    return not s.has_trigger_signal


R_QUAL_01 = Rule(
    id="R-QUAL-01",
    description="Zero trigger coverage (no rain, SWI, or seismic signal at all) vetoes the "
    "score: absence of signal is not evidence of absence of risk.",
    priority=1000,
    condition=_r_qual_01,
    effect=Veto(reason="no_trigger_signal"),
    provenance="Direct response to audit finding (docs/research/audit-2026-07.md §5): the "
    "declared index silently multiplied by zero when data was simply missing, "
    "indistinguishable from a confirmed absence of risk.",
)


_CORRUPTED_RAIN_FLAGS = frozenset({"frozen_rain_signal", "implausible_rain_max"})


def _r_qual_02(s: TerritorySnapshot) -> bool | None:
    return bool(_CORRUPTED_RAIN_FLAGS & s.quality_flags)


R_QUAL_02 = Rule(
    id="R-QUAL-02",
    description="Rain feed confirmed frozen/implausible city-wide vetoes the score: a "
    "present-but-corrupted trigger reading is not more trustworthy than a missing one.",
    priority=999,
    condition=_r_qual_02,
    effect=Veto(reason="corrupted_rain_signal"),
    provenance="Closes the gap R-QUAL-01 left open: has_trigger_signal only checks for `None`, "
    "so SIATA's frozen 0.003mm reading (audit finding 2, docs/research/audit-2026-07.md §4) "
    "passed through as a 'confirmed' trigger value instead of tripping the veto. "
    "quality_flags is now populated at inference time by "
    "infrastructure/repositories/data_quality.py, reusing the same predicates "
    "monitoring/scraper_validator.py runs periodically.",
)

CATALOG: tuple[Rule, ...] = (
    R_GEO_01,
    R_GEO_02,
    R_GEO_03,
    R_GEO_04,
    R_HIST_01,
    R_EXPO_01,
    R_SEIS_01,
    R_QUAL_01,
    R_QUAL_02,
)
