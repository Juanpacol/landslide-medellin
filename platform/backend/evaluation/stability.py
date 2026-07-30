"""Counterfactual stability — perturbs each snapshot's rain-derived fields by a small
percentage and checks whether the resolved level/veto status changes (specs/007-experimental-
eval/spec.md). A ±5% perturbation is within SIATA's own measurement noise, not a real change in
conditions; a system that flips risk category under that kind of noise is unstable in a way that
matters operationally, independent of whether any ground-truth label exists to score against —
same "needs no real labels" property as `rule_coverage`/`explanation_faithfulness`
(`evaluation/primary_metrics.py`) and the ablation study (`evaluation/ablation.py`), whose
resolve-twice-and-diff pattern this reuses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from application.neurosymbolic.infer import resolve_verdict
from domain.rules.engine import Rule
from domain.rules.facts import TerritorySnapshot

DEFAULT_PERTURBATION_PCT = 0.05

# Fields perturbed together, as a proxy for "the rain measurement was slightly off" rather than
# "conditions changed" — perturbing only one would model a scenario (e.g. antecedent moisture
# shifting independently of 72h rain) that isn't what ±5% measurement noise looks like.
_RAIN_FIELDS = ("precip_72h_mm", "antecedent_mm")


@dataclass(frozen=True)
class StabilityCase:
    commune_id: str
    neural_score: float | None
    snapshot: TerritorySnapshot


@dataclass(frozen=True)
class StabilityExample:
    commune_id: str
    original_level: str
    perturbed_level: str
    original_vetoed: bool
    perturbed_vetoed: bool


@dataclass(frozen=True)
class StabilityResult:
    perturbation_pct: float
    n_cases: int
    n_eligible: int  # cases with at least one rain field to perturb
    n_level_changed: int
    n_vetoed_changed: int
    examples: tuple[StabilityExample, ...]

    @property
    def pct_level_changed(self) -> float:
        return round(self.n_level_changed / self.n_eligible, 4) if self.n_eligible else 0.0

    @property
    def pct_vetoed_changed(self) -> float:
        return round(self.n_vetoed_changed / self.n_eligible, 4) if self.n_eligible else 0.0


def _perturb(snapshot: TerritorySnapshot, *, pct: float) -> TerritorySnapshot | None:
    """Scales every non-`None` field in `_RAIN_FIELDS` by `(1 + pct)`. Returns `None` if the
    snapshot has no rain field to perturb — that case is excluded from the denominator, not
    counted as "stable"."""
    updates = {}
    for field_name in _RAIN_FIELDS:
        value = getattr(snapshot, field_name)
        if value is not None:
            updates[field_name] = round(value * (1.0 + pct), 4)
    if not updates:
        return None
    return replace(snapshot, **updates)


def counterfactual_stability(
    cases: list[StabilityCase],
    rules: tuple[Rule, ...],
    *,
    perturbation_pct: float = DEFAULT_PERTURBATION_PCT,
    max_examples: int = 5,
) -> StabilityResult:
    """Pure: no I/O. For each case with a rain field present, resolves the verdict twice
    (original vs. `perturbation_pct` perturbed) and reports how often the category or veto
    status flips under what should be noise, not signal."""
    n_level_changed = 0
    n_vetoed_changed = 0
    n_eligible = 0
    examples: list[StabilityExample] = []

    for case in cases:
        perturbed_snapshot = _perturb(case.snapshot, pct=perturbation_pct)
        if perturbed_snapshot is None:
            continue
        n_eligible += 1

        original = resolve_verdict(case.commune_id, case.neural_score, case.snapshot, rules=rules)
        perturbed = resolve_verdict(
            case.commune_id, case.neural_score, perturbed_snapshot, rules=rules
        )

        level_changed = perturbed.level != original.level
        vetoed_changed = perturbed.derivation.get("vetoed") != original.derivation.get("vetoed")
        if level_changed:
            n_level_changed += 1
        if vetoed_changed:
            n_vetoed_changed += 1

        if (level_changed or vetoed_changed) and len(examples) < max_examples:
            examples.append(
                StabilityExample(
                    commune_id=case.commune_id,
                    original_level=original.level,
                    perturbed_level=perturbed.level,
                    original_vetoed=bool(original.derivation.get("vetoed")),
                    perturbed_vetoed=bool(perturbed.derivation.get("vetoed")),
                )
            )

    return StabilityResult(
        perturbation_pct=perturbation_pct,
        n_cases=len(cases),
        n_eligible=n_eligible,
        n_level_changed=n_level_changed,
        n_vetoed_changed=n_vetoed_changed,
        examples=tuple(examples),
    )
