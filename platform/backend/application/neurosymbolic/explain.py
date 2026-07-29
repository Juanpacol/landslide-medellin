"""Deterministic explanation rendering — turns a `Verdict` (application/neurosymbolic/infer.py)
into an `ExplanationTree`, a flat list of typed, traceable nodes. `agent/risk_explanations.py`
consumes this tree and may only rephrase it; it may not introduce a statement that has no
matching node here. That's the difference between narrating a score and deriving an explanation
(specs/004-explanations/spec.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from application.neurosymbolic.infer import Verdict
from domain.rules.engine import Escalate, MultiplyScore, RaisePriority, SetFloor, Veto


@dataclass(frozen=True)
class ExplanationNode:
    kind: str  # "neural" | "rule" | "conflict" | "confidence"
    text: str
    source_id: str  # rule id, "neural", or "confidence"


@dataclass(frozen=True)
class ExplanationTree:
    nodes: tuple[ExplanationNode, ...]

    def source_ids(self) -> frozenset[str]:
        return frozenset(n.source_id for n in self.nodes)


_EFFECT_LABELS = {
    SetFloor: "sets a minimum risk level",
    Escalate: "escalates the risk level",
    MultiplyScore: "scales the risk score",
    RaisePriority: "raises operational priority",
    Veto: "vetoes the score as untrustworthy",
}


def _effect_label(effect: object) -> str:
    return _EFFECT_LABELS.get(type(effect), "affects the verdict")


def render(verdict: Verdict) -> ExplanationTree:
    """Pure: builds the tree strictly from `verdict.derivation` and `verdict.conflicts` —
    nothing here queries the DB or calls an LLM."""
    nodes: list[ExplanationNode] = []

    neural_score = verdict.derivation.get("neural_score")
    neural_level = verdict.derivation.get("neural_level")
    if neural_score is not None:
        nodes.append(
            ExplanationNode(
                kind="neural",
                text=f"Neural hazard estimate: {neural_score:.3f} ({neural_level}).",
                source_id="neural",
            )
        )
    else:
        nodes.append(
            ExplanationNode(
                kind="neural",
                text="No neural hazard estimate available for this run.",
                source_id="neural",
            )
        )

    for fired in verdict.derivation.get("fired_rules", []):
        nodes.append(
            ExplanationNode(
                kind="rule",
                text=f"{fired['id']}: {fired['description']} ({fired['provenance']})",
                source_id=fired["id"],
            )
        )

    for conflict in verdict.conflicts:
        rule_id = conflict.get("rule_id", "unknown")
        effect = conflict.get("effect", "unknown")
        if effect == "veto":
            text = f"{rule_id} vetoed the neural score: {conflict.get('reason')}."
        elif effect == "set_floor":
            text = (
                f"{rule_id} raised the level from {conflict.get('neural_level')} to "
                f"{conflict.get('resolved_level')} (rule floor)."
            )
        elif effect == "escalate":
            text = (
                f"{rule_id} escalated the level from {conflict.get('neural_level')} to "
                f"{conflict.get('resolved_level')}."
            )
        else:
            text = f"{rule_id} affected the verdict ({effect})."
        nodes.append(ExplanationNode(kind="conflict", text=text, source_id=rule_id))

    confidence_reason = "high data coverage" if verdict.confidence >= 0.6 else "limited data coverage"
    if verdict.derivation.get("vetoed"):
        confidence_reason = "vetoed: no trigger signal at all"
    nodes.append(
        ExplanationNode(
            kind="confidence",
            text=f"Confidence: {verdict.confidence:.2f} ({confidence_reason}).",
            source_id="confidence",
        )
    )

    return ExplanationTree(nodes=tuple(nodes))


def is_faithful(statement_source_ids: list[str], tree: ExplanationTree) -> bool:
    """True iff every claimed source id in `statement_source_ids` maps to a real node in
    `tree`. Used to reject an LLM rephrasing that invented a factor with no derivation behind
    it (specs/004-explanations/spec.md criterion 3)."""
    valid = tree.source_ids()
    return all(sid in valid for sid in statement_source_ids)
