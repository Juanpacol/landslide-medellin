"""`Signal` and the `Estimator` protocol — specs/006-neural-estimators/spec.md's answer to the
audit's finding that a single classifier with 6-of-7 commune-identifier features decided
everything (docs/research/audit-2026-07.md §3). Each evidence source becomes an independent,
normalized `[0,1]` estimate with its own declared uncertainty, instead of being forced into one
feature vector for one model to arbitrate.

These estimators are pure: they read fields already resolved onto a `TerritorySnapshot`
(`domain/rules/facts.py`), the same snapshot `domain/rules` reasons over. The actual DB fetch
that populates the snapshot happens in `application/neurosymbolic/infer.py` / `ml/hazard.py` —
kept separate on purpose, so every estimator here is testable with a hand-built snapshot and no
database, same discipline as `domain/rules/catalog.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.rules.facts import TerritorySnapshot


@dataclass(frozen=True)
class Signal:
    """One source's normalized estimate. `value` is `[0,1]` or `None` (no data — never a
    silent 0.0, same discipline as `domain/susceptibility.py`). `uncertainty` is `[0,1]`,
    1.0 meaning "no signal at all", declared per estimator below rather than learned (no real
    labels exist to fit it against — docs/research/audit-2026-07.md §8)."""

    value: float | None
    uncertainty: float
    source: str
    coverage: float  # fraction of this signal's expected inputs that were actually present


class Estimator(Protocol):
    def estimate(self, snapshot: TerritorySnapshot) -> Signal: ...
