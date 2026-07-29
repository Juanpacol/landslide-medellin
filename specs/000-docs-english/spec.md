# SPEC-000 — Documentation in English

## Problem

TEYVA's code, docstrings and docs are entirely in Spanish. This project is being reframed as an
AI-engineering research contribution (neuro-symbolic risk assessment); reviewers and future
collaborators need English documentation. Translating is mechanical, but touches nearly every
file, so it must happen first and cleanly, without functional change.

## Goal

`CLAUDE.md`, `docs/`, docstrings and comments are in English. Meaning is preserved exactly —
this is a translation pass, not a rewrite. User-facing output (Slack messages, LLM prompts,
frontend copy) stays in Spanish, since stakeholders (Gestión del Riesgo Medellín) are
Spanish-speaking.

## Non-goals

- Rewriting or restructuring documents beyond translation (except archiving `REFACTOR_PLAN.md`,
  which describes an abandoned rewrite unrelated to this project).
- Translating Slack payloads, LLM prompts, frontend strings, or DB-stored category labels.

## Acceptance criteria

1. `CLAUDE.md` is English; a one-line rule states code/docs = English, user-facing output = Spanish.
2. `docs/AGENTS.md`, `docs/RUNBOOK_MIGRATIONS.md`, `docs/DESIGN_SYSTEM.md` are English.
3. `docs/REFACTOR_PLAN.md` moved to `docs/archive/`, noted in `specs/README.md`.
4. The audit article is translated, trimmed, and lives at `docs/research/audit-2026-07.md`.
5. `platform/backend/domain/`, `application/`, `ml/`, `infrastructure/`, `api/`, `scraper/`
   docstrings and comments are English.
6. `pytest platform/backend/tests -q` is green, including Spanish-string assertions
   (`test_examples_in_prompts.py`, `test_slack_payloads.py`).
