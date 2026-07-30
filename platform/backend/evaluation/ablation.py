"""Ablation study — removes a layer of the neuro-symbolic system and measures
the delta on level and confidence (specs/007-experimental-eval/spec.md task
4). Needs no real labels: the question isn't "did it predict correctly" but
"did removing this layer change the answer", which is exactly what makes two
layers "interacting" rather than running as independent stages
(docs/adr/0003-conflict-resolution-precedence.md).

Scope note: "remove ontology" has no runtime ablation to run — the OWL
ontology (specs/001-ontology/) isn't executed at inference time (SWRL axioms
are the formal spec, not the runtime, per ADR-0002), so there's nothing in
`application/neurosymbolic/infer.py` for an ontology ablation to switch off.
Only `rules` and `quality` are implemented here; that asymmetry is itself
worth stating plainly in the paper rather than papering over.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from application.neurosymbolic.infer import Verdict, resolve_verdict
from domain.rules.facts import TerritorySnapshot

AblationTarget = Literal["rules", "quality"]


@dataclass(frozen=True)
class AblationCase:
    commune_id: str
    neural_score: float | None
    snapshot: TerritorySnapshot


@dataclass(frozen=True)
class AblationExample:
    commune_id: str
    full_level: str
    ablated_level: str
    full_confidence: float
    ablated_confidence: float


@dataclass(frozen=True)
class AblationResult:
    target: AblationTarget
    n_cases: int
    n_level_changed: int
    confidence_delta_mean: float  # mean(full - ablated); positive = ablation increased confidence
    examples: tuple[AblationExample, ...]

    @property
    def pct_level_changed(self) -> float:
        return round(self.n_level_changed / self.n_cases, 4) if self.n_cases else 0.0


def _without_quality_flags(snapshot: TerritorySnapshot) -> TerritorySnapshot:
    return replace(snapshot, quality_flags=frozenset())


def _ablated_verdict(target: AblationTarget, case: AblationCase) -> Verdict:
    if target == "rules":
        return resolve_verdict(case.commune_id, case.neural_score, case.snapshot, rules=())
    if target == "quality":
        return resolve_verdict(
            case.commune_id, case.neural_score, _without_quality_flags(case.snapshot)
        )
    raise ValueError(f"unknown ablation target: {target}")


def run_ablation(
    target: AblationTarget, cases: list[AblationCase], *, max_examples: int = 5
) -> AblationResult:
    """Pure: no I/O. Runs `resolve_verdict` twice per case (full vs. ablated)."""
    if target not in ("rules", "quality"):
        raise ValueError(f"unknown ablation target: {target}")

    n_changed = 0
    deltas: list[float] = []
    examples: list[AblationExample] = []

    for case in cases:
        full = resolve_verdict(case.commune_id, case.neural_score, case.snapshot)
        ablated = _ablated_verdict(target, case)
        deltas.append(full.confidence - ablated.confidence)

        if ablated.level != full.level:
            n_changed += 1
            if len(examples) < max_examples:
                examples.append(
                    AblationExample(
                        commune_id=case.commune_id,
                        full_level=full.level,
                        ablated_level=ablated.level,
                        full_confidence=full.confidence,
                        ablated_confidence=ablated.confidence,
                    )
                )

    mean_delta = round(sum(deltas) / len(deltas), 4) if deltas else 0.0
    return AblationResult(
        target=target,
        n_cases=len(cases),
        n_level_changed=n_changed,
        confidence_delta_mean=mean_delta,
        examples=tuple(examples),
    )
