# TEYVA — Project Context

Landslide risk monitoring platform for Medellín (19 comunas + corregimientos). Functional MVP:
real-time data ingestion, 7-day ML prediction, REST API, web dashboard with conversational AI and
Slack alerts.

**Language rule:** code, docstrings and documentation are in English. User-facing output (Slack
messages, LLM prompts, frontend copy, DB-stored category labels) stays in Spanish — stakeholders
(Gestión del Riesgo Medellín) are Spanish-speaking.

**Research track:** TEYVA is being extended into a neuro-symbolic risk-assessment system (ML +
ontology + rule engine + inference + explanations). See `specs/README.md` for the spec-driven
breakdown and `docs/research/audit-2026-07.md` for the empirical audit that motivated it.

## Architecture

```
teyva/
├── platform/
│   ├── backend/          # SINGLE Python package (PYTHONPATH points here)
│   │   ├── domain/       # PURE rules (no I/O): risk_rules.py (thresholds, categories,
│   │   │                 #   compute_alert_state) + communes.py (SINGLE source of territory)
│   │   ├── application/  # Use cases: predict_risk.py, fire_alerts.py, train_model.py
│   │   ├── infrastructure/
│   │   │   ├── repositories/  # Shared queries (latest prediction per commune, etc.)
│   │   │   └── external/      # HTTP/SDK clients: arcgis, slack, osrm, llm
│   │   ├── ml/           # ML engine: train.py, predict.py (inference), benchmark.py, models/
│   │   ├── scraper/      # siata (30min), dagrd (1h), ideam (6h), medellin_datos (24h), seismic
│   │   │   └── scheduler.py  # APScheduler daemon + health watchdog (Slack alert)
│   │   ├── db/           # SQLAlchemy async+sync, session.py, 12+ tables
│   │   ├── api/          # FastAPI: routes/ + auth.py (roles) + rate_limit.py + audit.py
│   │   ├── agent/        # Chat: Claude (primary) + Ollama (fallback), RAG, MCP
│   │   ├── rag/          # ChromaDB + sentence-transformers (2,127 chunks)
│   │   ├── alerts/       # Slack alert construction + Snake Line + evacuation
│   │   ├── constants.py  # ONLY operational config: cooldowns, scraper intervals
│   │   └── alembic/      # migrations (7+)
│   └── frontend/         # Next.js 16 + React 19 + Tailwind 4 + Radix/shadcn
│       ├── components/dashboard/  # map, KPIs, chat, history, rain monitor, health
│       └── lib/api.ts    # centralized fetch client
├── specs/                # Spec-driven development: one dir per spec (spec/plan/tasks)
├── .github/workflows/    # 6 crons: 5 scrapers + predict-risk (run alembic + write to Supabase)
└── docker-compose.yml    # local stack: db (fallback), ollama, backend, frontend, scraper, ml
```

**Golden rule:** all Python lives under `platform/backend/` as ONE package — modules are imported
as top-level (`from domain.communes...`, `from db.models...`). Do not split into separate root
folders: it breaks imports and workflows.

**Layers (dependency direction `api/scraper → application → domain/infrastructure`):**
- `domain/` imports NOTHING with I/O. `domain/communes.py` is the single definition of the
  territory: canonical id ("1".."21", the one used by DATA) vs official code ("01".."16",
  "50".."90", only for ArcGIS/cartography). Any new commune list = bug.
- **Entrypoints invoked by GitHub Actions do NOT move** (`python -m scraper.siata`,
  `python -m ml.predict`, `python -m ml.train`): they are thin wrappers delegating to
  `application/`.
- Alert composition (which checks run after ingestion/prediction/periodic) lives ONLY in
  `application/fire_alerts.py`.

## Database — ONE single source of truth

**Supabase (PostgreSQL) via Connection Pooler** is the DB for everything: GitHub Actions, local
Docker and hand-run development.

- Connection ALWAYS via the pooler (`aws-1-us-west-2.pooler.supabase.com:5432`, Session mode):
  the direct host `db.<ref>.supabase.co` is **IPv6-only** and doesn't resolve on most local
  networks.
- `DB_SSL=true` mandatory. asyncpg uses a TLS context without cert verification (Supabase signs
  with its own CA) — equivalent to `sslmode=require`; already handled in `db/session.py`.
- Docker-compose's `db` is only an **offline fallback** (if the root `.env` doesn't define
  `DATABASE_URL`).
- Schema: managed by Alembic. **Never edit already-applied migrations** — that caused real drift
  between Supabase and local. Schema change = new migration.
- **Apply migrations ONLY from already-pushed `main`.** Applying to Supabase and committing
  afterward leaves `alembic_version` pointing to a revision the repo doesn't know, and the 6 crons
  fail with `Can't locate revision` (happened on 2026-07-26). Guard:
  `python -m monitoring.migration_guard --json`; runbook in `docs/RUNBOOK_MIGRATIONS.md`. Crons no
  longer die from this — `.github/actions/db-migrate` skips the upgrade and keeps ingesting — but
  drift blocks any new migration until resolved.
- **DDL privilege separation.** The app role (`teyva_app`, the one in `DATABASE_URL`/
  `DATABASE_URL_SYNC`) **cannot do DDL**: `alembic upgrade head` from a laptop against Supabase
  fails by design. Migrations are applied by GitHub Actions with `DATABASE_URL_MIGRATE`, which
  exists only as a secret. To create/test a migration, use the local compose Postgres. Policy in
  `infrastructure/migrations/ddl_url.py`; setup SQL in `docs/sql/ddl_privilege_split.sql`.

## Running it

```bash
docker compose up            # full stack → http://localhost:3000

# Backend by hand:
cd platform/backend && export PYTHONPATH=.
uvicorn api.main:app --reload --port 8000
python -m ml.predict         # batch predictions
python -m scraper.scheduler  # scraper daemon + watchdog
alembic upgrade head         # migrations

# Frontend by hand:
cd platform/frontend && pnpm dev
```

## Data and ML

- **Sources:** SIATA (rain), IDEAM (weather), DAGRD (emergencies), GeoMedellín (geographic
  features). Scrapers dedupe by `source_row_id` — `records_valid=0` with `ok` status means "no
  NEW events", not an error.
- **Model:** XGBoost. AUC-ROC 0.944, recall 0.999 (conservative). SMOTE for imbalance (26
  positives / 8,429 samples). **This metric is invalid** — see
  `docs/research/audit-2026-07.md`: the 26 positives came from synthetic events, and once the
  `is_synthetic` filter was applied correctly, 0 usable positives remained. The declared
  `susceptibility × trigger` index (`domain/susceptibility.py`, `ml/hazard.py`) exists precisely
  to replace it; `application/predict_risk.py` runs it through
  `application/neurosymbolic/infer.py`, combined with `domain/rules/` — see `specs/003-inference-engine/`.
- **ML pipeline governance** (`ml/train.py`): the 4 artifacts (`best_model.pkl`, `scaler.pkl`,
  `feature_names.json`, `metrics.json`) are written TOGETHER and only if training completes; an
  aborted run writes `last_train_attempt.json` (gitignored) and does NOT touch production.
  `metrics.json` carries `trained_at` + `git_commit_sha`. Extra metrics: `train_auc_temporal`
  (past→future temporal validation) and `benchmark_auc` (fixed snapshot in
  `ml/models/benchmark.json`, freeze with `python -m ml.benchmark --freeze`).
- **Synthetic events:** `landslide_events.is_synthetic=true` (144, generated by
  `scraper/ingest_synthetic_events.py` with Snake Line) are used to calibrate the Snake Line and
  are EXCLUDED from classifier training — training and validating with the same heuristic is
  circular contamination. The filter lives in `infrastructure/repositories/landslide_events.py`.
- **Risk thresholds:** ONLY in `domain/risk_rules.py` (`risk_level_from_score`): medium 0.35 /
  high 0.65 / critical 0.90. Categories are stored lowercase, no accents (`critico`); presentation
  via `display_label()`.

## Chat + RAG

`LLM_PROVIDER=anthropic` (default, `claude-haiku-4-5`) with automatic fallback to Ollama
(`llama3.2`). Both share the prompt and the 5 tools in `agent/rag_tools.py`. RAG on ChromaDB with
automatic source citations (contextvars). `ENABLE_RAG=true` activates it. Conversation history is
served at `GET /api/chat/sessions` (aggregates `agent_conversations`, no extra table).

## Security

- Mutating endpoints (`/predict-all`, `/predict-commune`, `PUT /rain/thresholds`,
  `GET|POST /rain/settings/webhook*`, `POST /alerts/report`) require
  `Authorization: Bearer $API_TOKEN` (`api/auth.py`, optional `viewer` role via
  `API_TOKEN_VIEWER`).
- **`ENV=production` without `API_TOKEN` = the backend DOES NOT START**
  (`assert_production_auth`). No token in dev = allows everything with a warning.
- In-memory per-IP rate limiting (`api/rate_limit.py`): chat 10 req/min, predict 5 req/min. If
  scaled to multiple workers, migrate to Redis.
- Append-only audit trail in the `audit_log` table (`api/audit.py::log_audit_event`): thresholds,
  webhooks, manual predictions, reports. Stores a SHA-256 hash of the payload, never the raw
  payload.
- `load_dotenv` calls use `override=False`: the real environment ALWAYS wins over `.env` (an empty
  `API_TOKEN=` in `.env` once overwrote the real token).
- CORS restricted via `ALLOWED_ORIGINS`.
- **Never** commit secrets: `.env` is gitignored; `.env.example` has placeholders only. (A real
  password was leaked in history once — rotated. Don't repeat it.)

## Alerts and monitoring

`alerts/slack.py` — 3 types with cooldown in `app_settings`: rain over threshold, critical risk,
and **downed scrapers** (consecutive failures OR staleness — silence > 3× interval, covers the
"GitHub Actions got disabled silently" case). The watchdog runs in the scheduler every 30 min.
Webhook: env `SLACK_WEBHOOK_URL` or UI (DB).

Agents in `monitoring/` (results → `agent_run_logs`, Slack via `notify.py`): `api_health`,
`ml_drift`, `scraper_validator` and `migration_guard` (Alembic DB↔repo drift). **Anti-noise rule:**
in `ok` state use `log_agent_run`, NEVER `fire_agent_alert` — the latter always posts to Slack, and
with agents running every 15–30 min that drowns out real alerts. Notify on failure and on
recovery.

Every failed workflow notifies Slack via `.github/actions/notify-failure` (pure bash+curl: works
even if `pip install` failed; only notifies the ok→failure transition).

**Known gotcha:** GitHub disables crons after 60 days without commits (`disabled_inactivity`). If
sources look down, check `gh workflow list` first.

## Conventions

- Python: type hints mandatory, async for I/O, snake_case. TypeScript: strict, camelCase,
  PascalCase components, Tailwind styles + tokens in `app/globals.css`.
- Prompt tests: `/eval-prompt chat_rag|risk_explanations|slack_webhooks` (reports in
  `tests/evals/eval_results/`).
- Don't test only the happy path; scrapers are tested against real data.
- Update this file if the architecture changes.

## Contact

Owner: Juan Pablo Botero (jbotero@aztia.co) · Stakeholder: Gestión del Riesgo Medellín

**Last updated:** July 2026 (neuro-symbolic research track + English documentation)
