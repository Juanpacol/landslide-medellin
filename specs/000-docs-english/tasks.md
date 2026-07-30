- [x] Translate `CLAUDE.md`, add English-code/Spanish-output rule (verifies: readable diff, rule present)
- [x] Translate `docs/AGENTS.md`, `docs/RUNBOOK_MIGRATIONS.md`, `docs/DESIGN_SYSTEM.md` (verifies: no meaning drift)
- [x] Archive `docs/REFACTOR_PLAN.md` to `docs/archive/`, note in `specs/README.md` (verifies: file moved, link updated)
- [x] Translate + trim audit article to `docs/research/audit-2026-07.md` (verifies: §3/4/8/9 kept, §6 replaced by pointer)
- [x] Translate `domain/` docstrings and comments (verifies: `pytest tests/test_domain_validation.py test_susceptibility.py -q` — full suite 323 passed, 12 skipped, no regressions). User-facing Spanish strings kept as-is per the language rule: `_DISPLAY_LABELS`, `_ALERT_LEVEL`, `ALERT_STATE_ACTIONS`, `CALIBRATION_NOTE`, PII redaction markers, `ValidationError` messages, `_HAZARD_SCORES` keys (match GeoMedellín's source data verbatim).
- [ ] Translate `application/` docstrings and comments (verifies: `pytest tests/test_predict_risk_error_handling.py -q`)
- [ ] Translate `ml/` docstrings and comments (verifies: `pytest tests/test_feature_registry.py -q`)
- [ ] Translate `infrastructure/` docstrings and comments (verifies: `pytest tests/test_ddl_url.py -q`)
- [ ] Translate `api/` docstrings and comments (verifies: `pytest tests/test_rate_limit.py -q`)
- [ ] Translate `scraper/` docstrings and comments (verifies: `pytest tests/test_seismic_dedup.py -q`)
- [ ] Full suite green (verifies: `pytest platform/backend/tests -q`, including `test_examples_in_prompts.py`, `test_slack_payloads.py`)

Note: new modules written during SPEC-001..007 (domain/rules/, domain/quality.py,
application/neurosymbolic/, ml/estimators/, kg/, evaluation/, infrastructure/ontology/) were
authored in English directly and don't need translation. The remaining scope here is the
pre-existing Spanish-language modules from before this session.
