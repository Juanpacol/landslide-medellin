# SPEC-004 — Explanations (XAI)

## Problem

`agent/risk_explanations.py` has the LLM narrate a score and invent plausible-sounding factors —
not derive them. Nothing ties its output to what actually fired. It also duplicates territory
data (`_IS_LADERA`, `_NOMBRES`) that already lives correctly in `domain/communes.py`, and the
duplicate is wrong for corregimientos.

## Goal

Explanations are derived, not narrated: a deterministic renderer turns `Verdict.derivation`
(SPEC-003) into a structured explanation tree, and the LLM's only job is to rephrase it —
every stated factor must trace back to a derivation node.

## Non-goals

- Changing the neural estimators or rule catalog.
- A new frontend framework — extend the existing `comuna-profile.tsx` / `model-features-panel.tsx`.

## Acceptance criteria

1. `application/neurosymbolic/explain.py::render()` turns a `Verdict` into an `ExplanationTree`:
   neural contribution, each fired rule with provenance, conflict resolutions, confidence and its
   cause.
2. SHAP explains the neural share only when the estimator is tree-based; for the declared-weight
   index, the renormalized component weights (`susceptibility_breakdown`) are reported instead —
   never fabricated attributions.
3. `agent/risk_explanations.py` is refactored so every `factors` entry maps 1:1 to a derivation
   node; a faithfulness check rejects any that doesn't.
4. `_IS_LADERA` and `_NOMBRES` are deleted from `risk_explanations.py`; `domain/communes.py` is
   the only source.
5. Frontend derivation panel in `comuna-profile.tsx` shows neural score, fired rules, overrides,
   confidence.
6. Tests: faithfulness, determinism without an API key, all four risk levels covered.
