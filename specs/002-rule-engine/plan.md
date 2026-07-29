# SPEC-002 — plan.md

## Architecture

Lives entirely in `domain/` — pure, no I/O, following the existing convention of
`domain/susceptibility.py` and `domain/risk_rules.py`. `application/neurosymbolic/infer.py`
(SPEC-003) is the only caller; it builds the `TerritorySnapshot` from DB data and owns the I/O.

## Files touched

- `domain/rules/__init__.py`
- `domain/rules/facts.py` — frozen `TerritorySnapshot` dataclass.
- `domain/rules/engine.py` — `Rule`, effect types, `RuleTrace`, `evaluate()`.
- `domain/rules/catalog.py` — the 8 rules, each with `provenance`.
- `domain/quality.py` — `DataQualityScore`, predicates lifted from `monitoring/scraper_validator.py`
  (that module imports from here afterward, not the reverse).
- `docs/adr/0002-rule-engine-typed-not-experta-not-swrl.md`.

## Interfaces

```python
@dataclass(frozen=True)
class TerritorySnapshot:
    commune_id: str
    slope_p90_deg: float | None
    twi_p90: float | None
    ndvi_min: float | None
    hazard_fraction: float | None
    precip_72h_mm: float | None
    antecedent_mm: float | None
    swi_pct: float | None
    seismic_intensity: float | None
    prior_event_count: float | None
    nearest_critical_facility_m: float | None
    quality_flags: frozenset[str]

class Effect: ...  # SetFloor | Escalate | MultiplyScore | RaisePriority | Veto

@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    priority: int
    condition: Callable[[TerritorySnapshot], bool]
    effect: Effect
    provenance: str

@dataclass(frozen=True)
class RuleTrace:
    fired: list[Rule]      # priority order
    not_evaluable: list[Rule]

def evaluate(snapshot: TerritorySnapshot) -> RuleTrace: ...
```

## Sequencing

Depends only on existing `domain/susceptibility.py` and `domain/risk_rules.py` constants.
Blocks SPEC-003 (inference engine consumes `RuleTrace`) and the SWRL cross-check test in SPEC-001.
