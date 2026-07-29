"""Primary evaluation metrics — the ones that don't need real landslide labels
(specs/007-experimental-eval/spec.md). The surrogate classification metrics (accuracy/F1/AUC on
the synthetic Snake Line benchmark) live separately and must always be captioned as a surrogate;
these are the honest, defensible numbers: how much of the rule catalog actually gets evidence to
evaluate, and whether an LLM-rephrased explanation stays faithful to its derivation.
"""

from __future__ import annotations

from dataclasses import dataclass

from application.neurosymbolic.explain import ExplanationTree, is_faithful
from domain.rules.engine import Rule, evaluate
from domain.rules.facts import TerritorySnapshot


@dataclass(frozen=True)
class RuleCoverageReport:
    """Per-rule and aggregate coverage across a set of snapshots (one per commune-run)."""

    n_snapshots: int
    fire_rate_by_rule: dict[str, float]  # rule id -> fraction of snapshots where it fired
    evaluable_rate_by_rule: dict[str, float]  # fraction where it could be evaluated at all
    pct_snapshots_with_any_fired_rule: float


def rule_coverage(snapshots: list[TerritorySnapshot], rules: tuple[Rule, ...]) -> RuleCoverageReport:
    """Pure: runs `domain.rules.engine.evaluate` over every snapshot and aggregates.

    This is the metric SPEC-002's `RuleTrace.not_evaluable` was built to feed: a rule that
    never has the data to fire is a coverage gap in the pipeline (e.g. terrain features not yet
    ingested — specs/006-neural-estimators/tasks.md), not a "the rule doesn't apply" result.
    """
    n = len(snapshots)
    fired_counts: dict[str, int] = {r.id: 0 for r in rules}
    evaluable_counts: dict[str, int] = {r.id: 0 for r in rules}
    any_fired = 0

    for snapshot in snapshots:
        trace = evaluate(snapshot, rules)
        fired_ids = {r.id for r in trace.fired}
        not_evaluable_ids = {r.id for r in trace.not_evaluable}
        if fired_ids:
            any_fired += 1
        for rule in rules:
            if rule.id in fired_ids:
                fired_counts[rule.id] += 1
            if rule.id not in not_evaluable_ids:
                evaluable_counts[rule.id] += 1

    if n == 0:
        return RuleCoverageReport(0, {r.id: 0.0 for r in rules}, {r.id: 0.0 for r in rules}, 0.0)

    return RuleCoverageReport(
        n_snapshots=n,
        fire_rate_by_rule={rid: count / n for rid, count in fired_counts.items()},
        evaluable_rate_by_rule={rid: count / n for rid, count in evaluable_counts.items()},
        pct_snapshots_with_any_fired_rule=round(any_fired / n, 4),
    )


@dataclass(frozen=True)
class FaithfulnessReport:
    n_statements: int
    n_faithful: int

    @property
    def faithfulness_rate(self) -> float:
        return round(self.n_faithful / self.n_statements, 4) if self.n_statements else 0.0


def explanation_faithfulness(
    statements: list[tuple[list[str], ExplanationTree]],
) -> FaithfulnessReport:
    """`statements` is a list of (claimed_source_ids, tree) pairs — one per generated
    explanation. Reuses `application/neurosymbolic/explain.py::is_faithful`, the same check
    that (once wired in, per specs/004-explanations/tasks.md) gates individual LLM
    explanations at generation time; here it's aggregated into one rate across a batch."""
    n_faithful = sum(1 for source_ids, tree in statements if is_faithful(source_ids, tree))
    return FaithfulnessReport(n_statements=len(statements), n_faithful=n_faithful)
