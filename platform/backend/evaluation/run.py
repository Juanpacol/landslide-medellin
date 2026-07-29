"""Four-arm comparison harness (specs/007-experimental-eval/spec.md).

Scope note: this is the pure, DB-free comparison of what each arm *does* with a given neural
score and territory snapshot — it does not itself run the classifier, query Postgres, or
reconstruct `ml/benchmark.py`'s frozen synthetic snapshot. That wiring (`evaluate_benchmark`
already exists in `ml/benchmark.py` for the classifier path) is future work — see
specs/007-experimental-eval/tasks.md. What's here is real and testable now: given the same
input, do the four arms actually disagree, and how.

Arms:
- `ml_only`      — the raw classifier/neural score, thresholded, no symbolic layer at all.
  This is what production did before SPEC-003 (`domain/risk_rules.py`'s old two-stage split).
- `declared_index` — the susceptibility x trigger score (`ml/hazard.py`), thresholded, still
  no symbolic layer. What production did between the audit and SPEC-003's wiring.
- `rules_only`   — no neural input at all (`neural_score=None`, base level "bajo"), only
  `domain/rules` effects. Shows what the symbolic layer alone can say.
- `neurosymbolic` — `application/neurosymbolic/infer.py::resolve_verdict`, the full system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from application.neurosymbolic.infer import Verdict, resolve_verdict
from domain.risk_rules import risk_level_from_score
from domain.rules.catalog import CATALOG
from domain.rules.facts import TerritorySnapshot

Arm = Literal["ml_only", "declared_index", "rules_only", "neurosymbolic"]
ARMS: tuple[Arm, ...] = ("ml_only", "declared_index", "rules_only", "neurosymbolic")


@dataclass(frozen=True)
class ArmResult:
    arm: Arm
    commune_id: str
    score: float | None
    level: str
    used_rules: bool


def run_arm(arm: Arm, commune_id: str, neural_score: float | None, snapshot: TerritorySnapshot) -> ArmResult:
    if arm in ("ml_only", "declared_index"):
        level = risk_level_from_score(neural_score)
        return ArmResult(arm=arm, commune_id=commune_id, score=neural_score, level=level, used_rules=False)

    if arm == "rules_only":
        verdict: Verdict = resolve_verdict(commune_id, None, snapshot, rules=CATALOG)
        return ArmResult(arm=arm, commune_id=commune_id, score=None, level=verdict.level, used_rules=True)

    if arm == "neurosymbolic":
        verdict = resolve_verdict(commune_id, neural_score, snapshot, rules=CATALOG)
        return ArmResult(
            arm=arm, commune_id=commune_id, score=verdict.score, level=verdict.level, used_rules=True
        )

    raise ValueError(f"unknown arm: {arm}")


def run_all_arms(commune_id: str, neural_score: float | None, snapshot: TerritorySnapshot) -> dict[Arm, ArmResult]:
    return {arm: run_arm(arm, commune_id, neural_score, snapshot) for arm in ARMS}


def arms_disagree(results: dict[Arm, ArmResult]) -> bool:
    """True if the four arms don't all land on the same risk level — the case worth reporting
    in the paper's comparison table."""
    levels = {r.level for r in results.values()}
    return len(levels) > 1
