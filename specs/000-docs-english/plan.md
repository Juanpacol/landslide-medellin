# SPEC-000 — plan.md

## Architecture

Documentation-only; no runtime code paths change. Touches every layer's docstrings but not
their behavior.

## Files touched

- `CLAUDE.md` — translated in place.
- `docs/AGENTS.md`, `docs/RUNBOOK_MIGRATIONS.md`, `docs/DESIGN_SYSTEM.md` — translated in place.
- `docs/REFACTOR_PLAN.md` → `docs/archive/REFACTOR_PLAN.md` — moved, untranslated (archived).
- `docs/articulo-teyva-neurosimbolico.md` → `docs/research/audit-2026-07.md` — translated,
  trimmed (§6 replaced by a pointer to `specs/`).
- `platform/backend/{domain,application,ml,infrastructure,api,scraper}/**/*.py` — docstrings
  and comments translated in place, module by module, one commit per module group.

## Interfaces

None — this spec introduces no code.

## Sequencing

No dependencies. Blocks nothing functionally, but should land first so all subsequent specs are
authored in English from the start.
