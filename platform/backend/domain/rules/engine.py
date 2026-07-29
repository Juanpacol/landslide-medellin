"""Pure, typed, forward-chaining rule engine.

See `docs/adr/0002-rule-engine-typed-not-experta-not-swrl.md` for why this is a small
hand-written engine and not `experta` or a SWRL runtime. `evaluate()` is a pure function of a
`TerritorySnapshot`: same input, same `RuleTrace`, every time — no I/O, no hidden state, no
randomness. `application/neurosymbolic/infer.py` (not this module) applies the effects and
decides the final verdict; this module only fires rules and records why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from domain.rules.facts import TerritorySnapshot


@dataclass(frozen=True)
class SetFloor:
    """Effect: the final risk level can never be lower than `level`."""

    level: str


@dataclass(frozen=True)
class Escalate:
    """Effect: raise the risk level by `steps` categories (bajo→medio→alto→critico)."""

    steps: int = 1


@dataclass(frozen=True)
class MultiplyScore:
    """Effect: scale the neural score by `factor` before re-deriving the level."""

    factor: float


@dataclass(frozen=True)
class RaisePriority:
    """Effect: raise operational priority without necessarily changing the risk category
    (e.g. proximity to a critical facility demands faster response at the same risk level)."""

    to: str = "max"


@dataclass(frozen=True)
class Veto:
    """Effect: the neural score cannot be trusted as-is; `reason` explains why. The inference
    engine (SPEC-003) treats this as the highest-precedence effect — it beats every other
    effect, including another rule's `SetFloor`."""

    reason: str


Effect = SetFloor | Escalate | MultiplyScore | RaisePriority | Veto


@dataclass(frozen=True)
class Rule:
    """One declarative rule. `effect` is always one of the types above — never arbitrary code,
    so every fired rule can be rendered as an explanation node (SPEC-004) without special-casing.
    """

    id: str
    description: str
    priority: int
    condition: Callable[[TerritorySnapshot], bool | None]
    effect: Effect
    provenance: str

    def evaluate(self, snapshot: TerritorySnapshot) -> bool | None:
        """True if fired, False if evaluated and did not fire, None if not evaluable
        (the condition needed a field that is `None` in the snapshot)."""
        return self.condition(snapshot)


@dataclass(frozen=True)
class RuleTrace:
    """Result of evaluating a rule set against one snapshot.

    `fired` is in priority order (highest first) — the order `application/neurosymbolic/infer.py`
    applies effects in. `not_evaluable` is what feeds SPEC-007's rule-coverage metric: a rule
    that can never evaluate because its inputs are missing is a coverage gap, not a "no" answer.
    """

    fired: tuple[Rule, ...]
    not_fired: tuple[Rule, ...]
    not_evaluable: tuple[Rule, ...]


def evaluate(snapshot: TerritorySnapshot, rules: tuple[Rule, ...]) -> RuleTrace:
    """Evaluate every rule in `rules` against `snapshot`. Pure: no I/O, no side effects."""
    fired: list[Rule] = []
    not_fired: list[Rule] = []
    not_evaluable: list[Rule] = []

    for rule in rules:
        try:
            result = rule.evaluate(snapshot)
        except Exception:
            # A condition that raises (e.g. comparing None) is a bug in the rule, not a
            # legitimate "not evaluable" — conditions must return None explicitly for that.
            raise
        if result is None:
            not_evaluable.append(rule)
        elif result:
            fired.append(rule)
        else:
            not_fired.append(rule)

    fired.sort(key=lambda r: (-r.priority, r.id))
    return RuleTrace(
        fired=tuple(fired),
        not_fired=tuple(not_fired),
        not_evaluable=tuple(not_evaluable),
    )
