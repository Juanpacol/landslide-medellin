# Documentation Guide

TEYVA is a landslide-risk monitoring platform for Medellín: real-time data ingestion, 7-day ML
prediction, a REST API, and a web dashboard with conversational AI and Slack alerts. It's also
the base for a neuro-symbolic risk-assessment research track (ML + ontology + rule engine +
inference + explanations).

Start with `CLAUDE.md` at the repo root if you need the authoritative, most-detailed description
of architecture, conventions, and known gotchas — everything below is a more scannable,
task-oriented complement to it.

## Where to go

| Doc | What's in it |
|---|---|
| [`README.md`](../README.md) | Project overview, stack, and module walkthrough (Spanish) |
| [`quick-start.md`](quick-start.md) | Get the stack running locally in under 5 minutes |
| [`architecture.md`](architecture.md) | Folder layout + data-flow and chat/RAG diagrams |
| [`api.md`](api.md) | REST endpoints: method, purpose, auth, curl examples |
| [`data-schema.md`](data-schema.md) | Database tables, key columns, relationships |
| [`troubleshooting.md`](troubleshooting.md) | Known issues: symptom → cause → fix |
| [`AGENTS.md`](AGENTS.md) | Monitoring agents (`api_health`, `ml_drift`, `scraper_validator`, `migration_guard`) |
| [`RUNBOOK_MIGRATIONS.md`](RUNBOOK_MIGRATIONS.md) | Alembic drift runbook |
| [`research/`](research/) | Neuro-symbolic research track, incl. `audit-2026-07.md` |
| [`adr/`](adr/) | Architecture decision records |
| [`sql/`](sql/) | Reference SQL (e.g. DDL privilege split) |
| [`../CLAUDE.md`](../CLAUDE.md) | Root project instructions — the single source of truth for architecture and conventions |

## Suggested onboarding order

1. `quick-start.md` — get something running.
2. `architecture.md` — see how the pieces fit together.
3. `api.md` + `data-schema.md` — the concrete surface you'll actually touch.
4. `troubleshooting.md` — avoid re-discovering already-known gaps.
5. `../CLAUDE.md` — read in full once; it's short and covers everything else (security, ML
   caveats, alert cooldowns, DB rules).
