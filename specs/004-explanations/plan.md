# SPEC-004 — plan.md

## Architecture

`application/neurosymbolic/explain.py` is pure transformation of `Verdict` (application layer,
no I/O). `agent/risk_explanations.py` stays the LLM-facing layer, now consuming the tree instead
of raw numbers.

## Files touched

- `application/neurosymbolic/explain.py` — `ExplanationTree`, `render(verdict) -> ExplanationTree`.
- `ml/estimators/shap_explainer.py` — SHAP wrapper for tree-based estimators, guarded fallback to
  declared weights.
- `agent/risk_explanations.py` — refactored to rephrase `ExplanationTree`; delete `_IS_LADERA`,
  `_NOMBRES`; add faithfulness check.
- `platform/frontend/components/dashboard/comuna-profile.tsx` — derivation panel.
- `tests/eval_results/` — new eval-prompt case for the rephrasing prompt.

## Interfaces

```python
@dataclass(frozen=True)
class ExplanationNode:
    kind: str  # "neural" | "rule" | "conflict" | "confidence"
    text: str
    source_id: str  # rule id, estimator name, etc.

@dataclass(frozen=True)
class ExplanationTree:
    nodes: list[ExplanationNode]

def render(verdict: Verdict) -> ExplanationTree: ...
```

## Sequencing

Depends on SPEC-003 (`Verdict`). No blockers downstream except SPEC-007 (faithfulness metric
reuses this module's faithfulness check).
