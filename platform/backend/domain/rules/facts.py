"""`TerritorySnapshot` — the only input the rule engine ever sees.

Pure, frozen, no I/O. Built by `application/neurosymbolic/infer.py` from DB data; the engine in
`domain/rules/engine.py` never queries anything itself, so every rule is testable with a
hand-built snapshot and no database.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TerritorySnapshot:
    """One commune's evidence at one point in time.

    Fields mirror `domain/susceptibility.py`'s inputs (`slope_p90_deg`, `twi_p90`, `ndvi_min`,
    `hazard_fraction`) and `domain/risk_rules.py`'s trigger inputs (precipitation, SWI, seismic),
    plus what the rule catalog needs beyond the neural score: historical proximity, critical
    infrastructure exposure, and data-quality flags (`domain/quality.py`).

    `None` means "no data", never "zero" — the same discipline `susceptibility.py` follows, and
    for the same reason (audit finding 2: a silent zero read as "no risk" instead of "no signal").
    """

    commune_id: str
    slope_p90_deg: float | None = None
    twi_p90: float | None = None
    ndvi_min: float | None = None
    hazard_fraction: float | None = None
    precip_72h_mm: float | None = None
    antecedent_mm: float | None = None
    swi_pct: float | None = None
    seismic_intensity: float | None = None
    prior_event_count: float | None = None
    nearest_critical_facility_m: float | None = None
    quality_flags: frozenset[str] = field(default_factory=frozenset)

    @property
    def has_trigger_signal(self) -> bool:
        """False when rain, SWI and seismic are all unknown — the zero-coverage case
        `R-QUAL-01` vetoes rather than silently scoring as safe."""
        return any(
            v is not None
            for v in (self.precip_72h_mm, self.antecedent_mm, self.swi_pct, self.seismic_intensity)
        )
