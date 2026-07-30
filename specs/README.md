# TEYVA Neuro-Symbolic — Spec Index

See `docs/SPEC_PROCESS.md` for how specs work. Status: `draft` → `planned` → `in-progress` → `done`.

| Spec | Title | Status | Tests |
|---|---|---|---|
| [000](000-docs-english/) | Documentation in English | in-progress (domain/ + application/ done, ml/infrastructure/api/scraper pending) | `pytest tests -q` (no regressions) |
| [001](001-ontology/) | Territory ontology (OWL) | in-progress (T-Box + A-Box done, SWRL pending) | `tests/test_ontology.py` |
| [002](002-rule-engine/) | Rule engine | done (validator wiring pending) | `tests/test_rules_engine.py`, `tests/test_rules_catalog.py`, `tests/test_domain_quality.py` |
| [003](003-inference-engine/) | Inference engine | done (migration skipped, reused JSONB) | `tests/test_infer_neurosymbolic.py` |
| [004](004-explanations/) | Explanations (XAI) | in-progress (renderer done, LLM wiring + frontend pending) | `tests/test_explain_render.py`, `tests/test_risk_explanations_communes.py` |
| [005](005-knowledge-graph/) | Knowledge graph | in-progress (static territory graph done, Postgres A-Box pending) | `tests/test_kg_build.py` |
| [006](006-neural-estimators/) | Neural estimators | in-progress (Signal protocol + 3 estimators done, XGBoost wrapping + terrain ingestion pending) | `tests/test_train_label_collapse_alert.py`, `tests/test_estimators.py` |
| [007](007-experimental-eval/) | Experimental evaluation | in-progress (primary metrics + 4-arm harness done, paper/CI/rubric pending) | `tests/test_evaluation_primary_metrics.py`, `tests/test_evaluation_run.py` |

Order: 000 first (touches everything). 001 → 002 → 003 → 004 sequential (each depends on the
previous). 005 and 006 in parallel after 002. 007 last. 006's terrain ingestion task can start
immediately, independent of everything else.

`docs/archive/REFACTOR_PLAN.md` — abandoned Go/HTMX rewrite plan, archived (SPEC-000), unrelated
to this effort.
