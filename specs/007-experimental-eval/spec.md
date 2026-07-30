# SPEC-007 — Experimental Evaluation

## Problem

There are no real landslide labels (0 usable positives, per audit). A conventional
accuracy/precision/recall/F1/AUC comparison table would measure agreement with the Snake Line
heuristic that generated its own labels — the exact circularity the audit exposed. The evaluation
must be honest about this while still producing a real experimental contribution.

## Goal

A dual-track evaluation: surrogate classification metrics on the synthetic benchmark, clearly
labelled as such, plus a primary evaluation track the data actually supports — rule coverage,
explanation faithfulness, expert agreement, uncertainty behaviour under ablation, and inference
latency — across four arms (ML-only, rules-only, neuro-symbolic, current declared index).

## Non-goals

- Claiming supervised performance gains the data cannot support.
- Waiting on a real event dataset before evaluating (the ablation study needs no real labels).

## Acceptance criteria

1. Four-arm benchmark harness extends `ml/benchmark.py`'s frozen-snapshot pattern.
2. Surrogate metrics table is captioned as a surrogate on synthetic labels, with the circularity
   stated in the same table's notes.
3. Primary metrics computed: rule coverage %, per-rule fire rate, explanation faithfulness %
   (via SPEC-004's faithfulness check), expert agreement (20-case DAGRD rubric, Cohen's κ),
   confidence-under-ablation delta, inference latency p50/p95, counterfactual stability under
   ±5% rain perturbation (`evaluation/stability.py::counterfactual_stability` — a system that
   flips risk category under noise within SIATA's own measurement error is unstable in a way
   that matters operationally, independent of ground-truth labels).
4. Ablation study: remove ontology / remove rules / remove quality layer, report delta on primary
   metrics.
5. `docs/research/paper.md` written: problem, audit findings, architecture, evaluation,
   limitations, related work, reproducibility.
6. CI workflow `neurosymbolic-eval` writes results to `evaluation/results/`.
