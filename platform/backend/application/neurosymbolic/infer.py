"""Inference engine — combines the neural hazard score (`ml/hazard.py`) with the symbolic rule
trace (`domain/rules`) into one `Verdict`, replacing the two-stage "model never learns from
rules, rules never predict" pipeline `domain/risk_rules.py` documents today.

The pure decision logic (`resolve_verdict`) takes no I/O — it's a function of a neural score and
a `RuleTrace`, so every conflict-resolution case is a one-line unit test. `infer_commune` /
`infer_all` are the only async, DB-touching parts: they build a `TerritorySnapshot` and call
`ml.hazard.hazard_by_commune` (already assembling susceptibility × trigger for all 21 communes in
one batch — that contract is preserved here, not reimplemented).

Conflict-resolution precedence (see `docs/adr/0003-conflict-resolution-precedence.md`):
`Veto` > rule floor > neural level. The neural score can never lower a rule-imposed floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from domain.risk_rules import (
    RISK_CATEGORIES,
    normalize_category,
    risk_level_from_score,
)
from domain.rules.catalog import CATALOG
from domain.rules.engine import (
    Escalate,
    MultiplyScore,
    RaisePriority,
    RuleTrace,
    SetFloor,
    Veto,
    evaluate,
)
from domain.rules.facts import TerritorySnapshot
from domain.susceptibility import CALIBRATION_NOTE, CALIBRATION_STATUS


@dataclass(frozen=True)
class Verdict:
    """The final output of one inference run for one commune. Everything downstream —
    `application/neurosymbolic/explain.py` (SPEC-004), the API, the frontend derivation panel —
    is a rendering of this object, never a re-derivation."""

    commune_id: str
    score: float | None
    level: str
    confidence: float
    priority: str
    derivation: dict[str, Any]
    conflicts: tuple[dict[str, Any], ...]
    calibration_status: str = CALIBRATION_STATUS

    def as_dict(self) -> dict[str, Any]:
        return {
            "commune_id": self.commune_id,
            "score": self.score,
            "level": self.level,
            "confidence": self.confidence,
            "priority": self.priority,
            "derivation": self.derivation,
            "conflicts": list(self.conflicts),
            "calibration_status": self.calibration_status,
        }


def _level_index(level: str) -> int:
    normalized = normalize_category(level)
    return RISK_CATEGORIES.index(normalized) if normalized in RISK_CATEGORIES else 0


def _level_at(index: int) -> str:
    return RISK_CATEGORIES[max(0, min(index, len(RISK_CATEGORIES) - 1))]


def _apply_effects(neural_level: str, trace: RuleTrace) -> tuple[str, list[dict[str, Any]], bool]:
    """Apply fired-rule effects on top of the neural level, in priority order.

    Returns (final_level, conflicts, vetoed). A `Veto` short-circuits: the level is kept for
    display but `vetoed=True` tells the caller to floor confidence and surface the reason —
    the score itself is never silently zeroed, it's flagged as untrustworthy (audit finding,
    docs/research/audit-2026-07.md §5).
    """
    level_idx = _level_index(neural_level)
    conflicts: list[dict[str, Any]] = []
    vetoed = False

    for rule in trace.fired:
        effect = rule.effect
        if isinstance(effect, Veto):
            vetoed = True
            conflicts.append(
                {
                    "rule_id": rule.id,
                    "effect": "veto",
                    "reason": effect.reason,
                    "neural_level": neural_level,
                }
            )
            continue
        if isinstance(effect, SetFloor):
            floor_idx = _level_index(effect.level)
            if floor_idx > level_idx:
                conflicts.append(
                    {
                        "rule_id": rule.id,
                        "effect": "set_floor",
                        "neural_level": _level_at(level_idx),
                        "rule_level": effect.level,
                        "resolved_level": effect.level,
                    }
                )
                level_idx = floor_idx
        elif isinstance(effect, Escalate):
            new_idx = level_idx + effect.steps
            if new_idx != level_idx:
                conflicts.append(
                    {
                        "rule_id": rule.id,
                        "effect": "escalate",
                        "neural_level": _level_at(level_idx),
                        "resolved_level": _level_at(new_idx),
                    }
                )
                level_idx = new_idx
        # MultiplyScore and RaisePriority don't change the category directly; MultiplyScore
        # affects `score` (handled by the caller), RaisePriority affects `priority` only.

    return _level_at(level_idx), conflicts, vetoed


def _resolve_priority(trace: RuleTrace) -> str:
    priorities = [r.effect.to for r in trace.fired if isinstance(r.effect, RaisePriority)]
    if "max" in priorities:
        return "max"
    if "elevated" in priorities:
        return "elevated"
    return "normal"


def _resolve_score(neural_score: float | None, trace: RuleTrace) -> float | None:
    if neural_score is None:
        return None
    score = neural_score
    for rule in trace.fired:
        if isinstance(rule.effect, MultiplyScore):
            score = max(0.0, min(1.0, score * rule.effect.factor))
    return round(score, 4)


def _confidence(snapshot: TerritorySnapshot, trace: RuleTrace, *, vetoed: bool) -> float:
    """Per-commune, per-run confidence — replaces the global static `CALIBRATION_STATUS` flag
    with a number that actually varies by how much evidence this specific run had.

    Not statistically calibrated (no real event series exists to calibrate against — see
    docs/research/audit-2026-07.md §6.4/§8): this is a declared, auditable formula, same
    honesty discipline as `domain/susceptibility.py`.
    """
    if vetoed:
        return 0.0

    tracked_fields = (
        snapshot.slope_p90_deg,
        snapshot.twi_p90,
        snapshot.ndvi_min,
        snapshot.hazard_fraction,
        snapshot.precip_72h_mm,
        snapshot.antecedent_mm,
        snapshot.swi_pct,
        snapshot.seismic_intensity,
    )
    coverage = sum(1 for v in tracked_fields if v is not None) / len(tracked_fields)

    flag_penalty = min(0.4, 0.1 * len(snapshot.quality_flags))
    not_evaluable_penalty = min(0.2, 0.02 * len(trace.not_evaluable))

    return round(max(0.0, min(1.0, coverage - flag_penalty - not_evaluable_penalty)), 4)


def resolve_verdict(
    commune_id: str,
    neural_score: float | None,
    snapshot: TerritorySnapshot,
    *,
    rules: tuple = CATALOG,
) -> Verdict:
    """Pure: no I/O. The only function that needs testing to cover every conflict-resolution
    case — `infer_commune`/`infer_all` are thin async wrappers around this."""
    trace = evaluate(snapshot, rules)
    neural_level = risk_level_from_score(neural_score)
    resolved_level, conflicts, vetoed = _apply_effects(neural_level, trace)
    resolved_score = _resolve_score(neural_score, trace)
    priority = _resolve_priority(trace)
    confidence = _confidence(snapshot, trace, vetoed=vetoed)

    derivation = {
        "neural_score": neural_score,
        "neural_level": neural_level,
        "fired_rules": [
            {
                "id": r.id,
                "description": r.description,
                "provenance": r.provenance,
                "priority": r.priority,
            }
            for r in trace.fired
        ],
        "not_evaluable_rules": [r.id for r in trace.not_evaluable],
        "vetoed": vetoed,
        "calibration_note": CALIBRATION_NOTE,
    }

    return Verdict(
        commune_id=commune_id,
        score=resolved_score,
        level=resolved_level,
        confidence=confidence,
        priority=priority,
        derivation=derivation,
        conflicts=tuple(conflicts),
    )


async def infer_commune(session, commune_id: str, *, as_of: date | None = None) -> Verdict:
    """One commune. Computes all 21 under the hood (see `ml.hazard.hazard_for_commune`'s own
    docstring for why) — for batch use, prefer `infer_all`."""
    all_verdicts = await infer_all(session, as_of=as_of)
    return all_verdicts.get(
        str(commune_id),
        resolve_verdict(str(commune_id), None, TerritorySnapshot(commune_id=str(commune_id))),
    )


async def infer_all(session, *, as_of: date | None = None) -> dict[str, Verdict]:
    """All 21 communes in one pass, preserving `ml.hazard.hazard_by_commune`'s batch contract."""
    from ml.hazard import hazard_by_commune

    hazards = await hazard_by_commune(session, as_of=as_of)

    out: dict[str, Verdict] = {}
    for commune_id, hazard in hazards.items():
        snapshot = TerritorySnapshot(
            commune_id=commune_id,
            hazard_fraction=hazard.susceptibility_components.get("hazard"),
            swi_pct=hazard.trigger_components.get("swi", 0.0) * 100.0
            if hazard.trigger_components.get("swi") is not None
            else None,
            antecedent_mm=hazard.trigger_components.get("antecedent"),
            precip_72h_mm=hazard.trigger_components.get("antecedent"),
            seismic_intensity=hazard.trigger_components.get("seismic"),
        )
        out[commune_id] = resolve_verdict(commune_id, hazard.score, snapshot)
    return out
