# SPEC-007 — plan.md

## Architecture

New top-level `evaluation/` package, read-only against production data plus the frozen benchmark
snapshot in `ml/models/benchmark.json`.

## Files touched

- `evaluation/__init__.py`, `evaluation/run.py` — four-arm harness.
- `evaluation/surrogate_metrics.py` — accuracy/precision/recall/F1/AUC on synthetic labels.
- `evaluation/primary_metrics.py` — coverage, faithfulness, latency.
- `evaluation/rubric.md` — 20-case DAGRD expert-agreement template.
- `evaluation/ablation.py` — ontology/rules/quality-layer ablations.
- `docs/research/paper.md`.
- `.github/workflows/neurosymbolic-eval.yml` — follows `.github/actions/notify-failure` convention.

## Interfaces

```python
def run_arm(arm: Literal["ml_only", "rules_only", "neurosymbolic", "declared_index"]) -> ArmResult: ...
def run_ablation(remove: Literal["ontology", "rules", "quality"]) -> AblationResult: ...
```

## Sequencing

Depends on SPEC-002 through SPEC-006 all being in place (it evaluates the assembled system).
Runs last.
