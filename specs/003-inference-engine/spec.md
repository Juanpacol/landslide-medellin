# SPEC-003 — Inference Engine

## Problem

Today the neural score and symbolic rules never interact: `risk_rules.py` explicitly documents
"the model never learns from these rules; the rules never predict" — two independent stages.
There is no arbitration when they disagree, and confidence is a single global static flag
(`CALIBRATION_STATUS`) instead of per-commune, per-run.

## Goal

`application/neurosymbolic/infer.py` combines the neural hazard score
(`ml/hazard.py::hazard_by_commune`) with the SPEC-002 rule trace, resolves conflicts by a
declared precedence, and emits a `Verdict` with score, level, per-commune confidence, and a full
derivation record — replacing the static calibration flag with something auditable per run.

## Non-goals

- Rendering the derivation as text (SPEC-004).
- Retraining or changing the neural estimators (SPEC-006).

## Acceptance criteria

1. `Verdict(score, level, confidence, derivation, conflicts, calibration_status)` is the single
   output type of inference.
2. Conflict precedence is declared and documented in an ADR: `Veto` > rule floor > neural level;
   the neural score cannot lower a rule-imposed floor; ties break by priority then rule id.
3. Every override is recorded in `conflicts` with both the neural and rule-driven values.
4. Confidence is computed per commune, per run, as a function of source coverage, active quality
   flags, and dependence on contaminated synthetic labels — not a global constant.
5. `application/predict_risk.py` is wired to use the inference engine; `risk_predictions` gains
   nullable columns for the derivation JSON via a new Alembic migration (never editing an applied
   one).
6. `GET /api/risk/comuna/{id}/detalle` includes the derivation; new `GET /api/risk/derivation/{id}`.
7. Tests cover: neural-only path, rule-override path, veto path, confidence monotonicity.
