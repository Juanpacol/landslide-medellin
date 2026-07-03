# TEYVA Project Context

## 📍 What is TEYVA?

TEYVA is a **landslide risk monitoring platform for Medellín, Colombia**. It's a production-ready MVP that integrates real-time data ingestion, machine learning predictions, REST APIs, and an interactive web dashboard with conversational AI.

**Status:** Live and functional (not planning stage). The system has trained models, active data pipelines, and working APIs serving real data.

---

## 🎯 Problem Statement

Medellín faces significant landslide risk due to geography and climate. Currently:
- Risk assessment is **fragmented** across multiple data sources (rainfall, events, terrain)
- Communication between technical teams and non-technical decision-makers is **slow**
- Early warning requires **hours of manual analysis**

TEYVA solves this by:
1. Centralizing dispersed data sources
2. Applying ML to predict risk 7 days ahead
3. Exposing predictions via dashboard + conversational AI
4. Enabling rapid communication of risk to stakeholders

---

## 🏗️ Project Structure (Single Source of Truth)

**Architectural decision:** All Python backend code lives under ONE package root
(`platform/backend/`) because `ml`, `scraper`, `etl`, `db`, `agent`, `api`, and
`integrations` are a single coupled package — they import each other as top-level
siblings (`from db.models...`, `from scraper.common...`, `from ml.features...`).
Do NOT split them across separate top-level folders; it breaks the import graph and
the GitHub Actions workflows. Conceptually, `ml/scraper/etl` are the "intelligence"
layer and `api/agent` are the "platform" layer, but they share `db/`.

```
teyva/
├── platform/
│   ├── backend/                # SINGLE Python package root (PYTHONPATH points here)
│   │   ├── ml/                 # --- Intelligence layer ---
│   │   │   ├── train.py        # XGBoost training pipeline
│   │   │   ├── predict.py      # Inference engine (run: python -m ml.predict)
│   │   │   ├── features.py     # Feature engineering
│   │   │   ├── evaluation.py   # Model metrics
│   │   │   └── models/         # Trained artifacts (best_model.pkl, scaler.pkl, metrics.json)
│   │   ├── scraper/            # Data ingestion (run: python -m scraper.<source>)
│   │   │   ├── scheduler.py    # APScheduler orchestration
│   │   │   ├── siata.py        # Rainfall (30 min)
│   │   │   ├── ideam.py        # Meteorology (6 h)
│   │   │   ├── dagrd.py        # Wildfire/landslide (1 h)
│   │   │   ├── medellin_datos.py # Municipal (24 h)
│   │   │   ├── geocode_events.py # Geographic event assignment
│   │   │   └── common.py       # Shared utils (retry, headers, logging)
│   │   ├── etl/
│   │   │   └── etl.py          # Legacy ETL (Supabase → PostgreSQL migration pending)
│   │   ├── db/                 # --- Shared data layer (used by ALL of the above) ---
│   │   │   ├── models/         # SQLAlchemy ORM (5 tables)
│   │   │   ├── session.py      # Async + sync connection pools
│   │   │   └── base.py         # Declarative base
│   │   ├── api/                # --- Platform layer: FastAPI ---
│   │   │   ├── main.py         # App init, CORS, routers
│   │   │   └── routes/         # risk.py, chat.py, scraper.py
│   │   ├── agent/              # Conversational AI (Ollama + tool-calling)
│   │   │   ├── chat.py               # Chat clásico (single response)
│   │   │   ├── chat_rag.py           # Chat con RAG + tools (Ollama loop)
│   │   │   ├── rag_tools.py          # 5 tools (search_knowledge, risk, events, rainfall, health)
│   │   │   ├── mcp_server.py         # FastMCP (expone las tools a clientes MCP externos)
│   │   │   ├── prompts.py, memory.py
│   │   ├── rag/                # Vector store + ingesta (ChromaDB)
│   │   │   ├── chroma_store.py       # ChromaDB persistence, búsqueda + detección de zona
│   │   │   └── data/                 # Chunks JSON (siata_hidromet, siata_geotecnia, dagrd_eventos, medellin_comunas)
│   │   ├── integrations/
│   │   │   └── agent_contracts.py  # Bridge: api → ml/agent
│   │   ├── alembic/            # Migrations (1: initial schema)
│   │   ├── app.py              # LEGACY: old Supabase-based API (to be deleted)
│   │   ├── setup_db.sql
│   │   └── requirements.txt
│   │
│   └── frontend/               # React + Next.js dashboard
│       ├── app/                # Next.js App Router
│       ├── components/
│       │   ├── dashboard/      # 8 main components (map, chart, chat, kpis...)
│       │   └── ui/             # 60 Radix UI / shadcn wrappers
│       ├── lib/api.ts          # Centralized fetch client
│       ├── hooks/
│       ├── package.json
│       └── next.config.mjs     # API proxy → localhost:8000
│
├── docs/                       # AGENTS.md, PLAN_AUDITORIA_14_DIAS.md, REFACTOR_PLAN.md
├── .github/workflows/          # 5 GitHub Actions (working-directory: platform/backend)
├── CLAUDE.md                   # This file
├── README.md
├── docker-compose.yml          # Ollama service
└── .env.example
```

### How to run (local dev)

```bash
cd platform/backend
export PYTHONPATH=.            # makes db/ml/scraper/agent importable as top-level
uvicorn api.main:app --reload --port 8000   # API
python -m ml.predict                         # batch predictions
python -m scraper.scheduler                  # scraper daemon
```

---

## ⚙️ Tech Stack

### Backend
- **Framework:** FastAPI + Uvicorn
- **Database:** PostgreSQL (async via asyncpg, sync via psycopg2)
- **ORM:** SQLAlchemy 2.0+ with async support
- **Migrations:** Alembic
- **Scheduling:** APScheduler (cron-like jobs)
- **HTTP Client:** httpx (async), requests (sync)
- **Parsing:** BeautifulSoup4

### Intelligence (ML & Scraper)
- **ML Framework:** scikit-learn
- **Model:** XGBoost (primary), RandomForest, LogisticRegression (alternatives)
- **Feature Balance:** imbalanced-learn (SMOTE)
- **Serialization:** joblib
- **Data Processing:** pandas, scipy
- **Geospatial:** geopandas

### Frontend
- **Framework:** Next.js 16.2.0 + React 19.2.4
- **Language:** TypeScript 5.7.3
- **Styling:** Tailwind CSS 4.2.0
- **UI Components:** Radix UI (60+), shadcn/ui wrappers
- **Charts:** Chart.js + Recharts
- **Maps:** Leaflet + React Leaflet
- **Forms:** react-hook-form + zod
- **Notifications:** Sonner

### RAG + Conversational AI
- **Vector Store:** ChromaDB (persistent, local)
- **Embeddings:** sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
- **LLM (primary):** Claude (Anthropic API) — `ANTHROPIC_MODEL` (default `claude-haiku-4-5`)
- **LLM (fallback):** Ollama (llama3.2 3B, local) — auto-fallback if Claude fails/unavailable, or forced via `LLM_PROVIDER=ollama`
- **Tool Protocol:** FastMCP (bridges the same tools to external MCP clients)

### Infrastructure
- **Containerization:** Docker (Ollama service, kept for the local fallback)
- **LLM:** Claude (Anthropic API, primary) + Ollama (local fallback, privacy-first offline mode)
- **CI/CD:** GitHub Actions (5 workflows: scraper jobs + ML predictions)

---

## 📊 Data Architecture

### Input Data Sources
1. **SIATA** - Real-time rainfall (30 min intervals)
2. **IDEAM** - Meteorological data (6 hour intervals)
3. **DAGRD** - Wildfire & landslide events (1 hour updates)
4. **Medellín Datos** - Municipal data (24 hour updates)

### Database Schema (5 core tables)

```
agent_conversations
├── session_id (indexed)
├── role (user | assistant)
├── content
└── created_at

landslide_events
├── source_row_id (origin ID)
├── fecha (event date)
├── tipo_emergencia (emergency type)
├── commune_id (indexed, refs 19 communes)
├── latitud, longitud
└── has_coords (geocoding success flag)

ml_features
├── commune_id (indexed)
├── reference_date
├── features (JSONB: 26 computed features)
├── precip_acum_7d (7-day rainfall)
├── n_events_window
└── created_at

risk_predictions
├── commune_id (indexed)
├── risk_score (0-1 probability)
├── risk_category (bajo|medio|alto|critico)
├── model_version
└── created_at

scraping_logs
├── source (siata|ideam|dagrd|medellin_datos)
├── status (started|completed|failed)
├── records_downloaded, valid, discarded
└── timestamps
```

### ML Model

**Selected Model:** XGBoost Classifier
- **AUC-ROC:** 0.944 (cross-validation)
- **Precision:** 0.736
- **Recall:** 0.999 (conservative, safety-first)
- **Threshold:** 0.3 (predicts positive to minimize false negatives)

**Input Features (7 total):**
- centroid_lat, centroid_lon
- densidadmax
- mean_precip_mm_snapshot
- precip_records, precip_sum_mm_day
- station_count

**Class Imbalance:** 26 positive cases in 8,429 samples → handled via SMOTE + stratified CV.

**Risk Category Thresholds:** ⚠️ **Currently inconsistent across modules** (P0 issue):
- risk.py: 0.25 / 0.50 / 0.75
- predict.py: 0.35 / 0.65 / 0.90
- chat.py: 0.30 / 0.60 / 0.80

→ Must unify in `constants.py`

---

## 🔌 API Endpoints

### Risk Endpoints
- `GET /api/risk/comunas` - GeoJSON of all communes + current risk
- `GET /api/risk/comuna/{id}` - Single commune data
- `GET /api/risk/comuna/{id}/detalle` - Rich detail (rainfall, events, predictions)
- `GET /api/risk/historia/{id}` - 30-day historical (rainfall + events + predictions)
- `GET /api/risk/estadisticas` - KPI summary
- `GET /api/risk/alerts` - High-risk communes (Alto/Crítico)
- `POST /api/risk/predict-all` - Trigger batch predictions
- `POST /api/risk/predict-commune` - Single prediction

### Chat Endpoints
- `POST /api/chat` - Send message, get reply (Claude primary, Ollama fallback + context)
- `GET /api/chat/history/{session_id}` - Fetch conversation history

### Scraper Endpoints
- `GET /api/scraper/logs` - List scraper runs
- `GET /api/scraper/status` - Overall scraper health

---

## 🤖 Conversational AI + RAG

**Mode:** Tool-calling loop. `LLM_PROVIDER=anthropic` (default) uses Claude; falls back
to Ollama automatically if `ANTHROPIC_API_KEY` is missing or the call fails. Both
providers share the same `SYSTEM_PROMPT`, tool suffix, and tool definitions in
`agent/rag_tools.py` — only the wire-format ("cableado") differs per provider, so
switching back to Ollama-only is just `LLM_PROVIDER=ollama`, no code changes.

**Features:**
1. **RAG (Retrieval-Augmented Generation)**
   - 2,127 chunks from 4 sources: SIATA HIDROMET, SIATA geotecnia, DAGRD eventos, Medellín comunas
   - ChromaDB + sentence-transformers embeddings (multilingual)
   - Smart zone detection: query mentions "Villatina" → filters chunks to that zone only
   
2. **5 Tools for model orchestration**
   - `search_knowledge`: Semantic search in PDFs + ArcGIS (with inline citas)
   - `get_risk_predictions`: Current ML risk score per commune
   - `get_recent_events`: DAGRD emergencies + landslide events
   - `get_rainfall_timeseries`: Rainfall accumulation (7d)
   - `get_scraper_health`: Status of data sources

3. **Source Attribution (📚 Footer)**
   - Every RAG query automatically records which PDFs/sources were consulted
   - Footer appended to response: "📚 Fuentes consultadas: HV_Villatina.pdf (págs. 1, 3, 7)"
   - Uses `contextvars` to safely track sources across async requests
   - **Independent of model** — works even if LLM hallucinates

**How to activate:**
```bash
export ENABLE_RAG=true
export LLM_PROVIDER=anthropic   # default; set ANTHROPIC_API_KEY in .env
# OR for fully local/offline:
export LLM_PROVIDER=ollama
ollama serve    # llama3.2 with tool-calling (local)
```

**Model behavior:**
- **Claude (Anthropic API, primary):** Better tool-call precision and instruction-following; small marginal cost per request.
- **Ollama (llama3.2 3B, local fallback):** Free, privacy-first, works offline; more prone to missed tool calls and minor hallucinations on ambiguous entities (e.g. barrio names not mapped to a comuna).

---

## 🚨 Critical Issues (P0 - MUST FIX)

1. **Inconsistent risk thresholds** (3 different mappings across modules)
2. **No API authentication** (all endpoints public, no JWT/bearer tokens)
3. **CORS wide open** (`allow_origins=["*"]`)
4. **Frontend hardcoded to localhost:8000** (can't be deployed)

→ See `docs/AUDIT_14DAYS.md` for detailed remediation plan.

---

## 🔄 Workflow & CI/CD

### GitHub Actions (5 Workflows)
1. **predict-risk.yml** - Runs every 6 hours: `python -m ml.predict`
2. **scraper-siata.yml** - Every 30 min (configured in scheduler)
3. **scraper-ideam.yml** - Every 6 hours
4. **scraper-dagrd.yml** - Every 1 hour
5. **scraper-medellin.yml** - Every 24 hours

All workflows:
- Checkout repo
- Install Python 3.11 + deps
- Run pipeline module
- Use GitHub Secrets for DB credentials

### Local Development

**Backend:**
```bash
cd platform/backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
export PYTHONPATH=.        # db/ml/scraper/agent importable as top-level
alembic upgrade head
uvicorn api.main:app --reload --port 8000
```

**Frontend:**
```bash
cd platform/frontend
pnpm install
pnpm dev  # runs on http://localhost:3000
```

**ML Training & Prediction:**
```bash
cd platform/backend
python -m ml.train      # Trains XGBoost, outputs artifacts
python -m ml.predict    # Runs inference, stores predictions
```

**Data Ingestion:**
```bash
cd platform/backend
python -m scraper.scheduler  # Starts APScheduler daemon
```

### Prompt Evaluation (Skill)

**Available:** `/eval-prompt` skill for measuring prompt quality across 3 critical modules:

```bash
# Evaluate chat RAG prompt against 13 test cases
/eval-prompt chat_rag --threshold 95 --verbose

# Evaluate risk explanation generation (10 test cases)
/eval-prompt risk_explanations --threshold 90

# Evaluate Slack webhook payload generation (5 test cases)
/eval-prompt slack_webhooks --threshold 85
```

**Output:** JSON reports saved to `tests/eval_results/` with accuracy %, pass/fail per test, and comparison vs previous runs.

**Workflow:** Edit prompt → Run `/eval-prompt` → See accuracy metric → Iterate until threshold passed → Deploy with confidence.

See [.claude/skills/eval-prompt.md](.claude/skills/eval-prompt.md) for full documentation and development workflow.

---

## 📈 Key Metrics & Monitoring

### Model Performance
- **AUC-ROC:** 0.944
- **Precision:** 0.736
- **Recall:** 0.999 (prioritizes catching positives)
- **Cross-validation:** 5-fold stratified

### System Health (to be implemented)
- Scraper freshness: Last successful run per source
- Data lag: How old is the most recent data point?
- Prediction coverage: % of 19 communes with recent predictions
- API latency: p50/p95/p99
- Chat availability: Ollama uptime

---

## 🎓 Code Conventions

### Python (Backend & Intelligence)
- **Type hints:** Required (PEP 484)
- **Async:** Use `async/await` for I/O
- **Logging:** Standard library `logging`, configure at startup
- **Error handling:** Explicit catches, graceful fallbacks
- **Imports:** Relative within modules, absolute for cross-module

### TypeScript (Frontend)
- **Strict mode:** Enabled in tsconfig.json
- **Components:** Functional with hooks
- **API calls:** Via `lib/api.ts` centralized client
- **Styling:** Tailwind classes + shadcn components

### Naming
- **Tables:** snake_case (SQL standard)
- **Columns:** snake_case
- **Python functions/variables:** snake_case
- **TypeScript functions/variables:** camelCase
- **Components:** PascalCase
- **Files:** kebab-case (frontend components), snake_case (backend modules)

---

## ✋ What NOT to Do (Mistakes to Avoid)

1. **Don't commit `.env` files** - Use `.env.example` template instead
2. **Don't hardcode thresholds** - Use constants module
3. **Don't ignore type hints** - They prevent runtime bugs
4. **Don't make API calls without auth** - All critical endpoints need JWT
5. **Don't skip migrations** - Always create new Alembic files for schema changes
6. **Don't test only happy path** - Include edge cases (empty data, API failures)
7. **Don't modify scraper logic without updating docs** - Scrapers are production-critical

---

## 🎯 Success Metrics for This Project

**MVP Complete When:**
- ✓ All 4 P0 security issues closed
- ✓ Test coverage > 70% (core paths)
- ✓ All 19 communes returning predictions hourly
- ✓ Chat responds to queries with data-backed answers (no hallucinations) — verified via `/eval-prompt chat_rag`
- ✓ Risk explanations have no vague language (verified via `/eval-prompt risk_explanations`)
- ✓ Scraper logs show all 4 sources healthy for 7+ days
- ✓ Dashboard loads in < 2 seconds

---

## 📞 Contacts & Resources

**Project Owner:** Juan Pablo Botero (jbotero@aztia.co)
**Tech Lead:** [Assign as needed]
**Stakeholder:** Medellín City Risk Management

**Key Documents:**
- Audit & Roadmap: `docs/AUDIT_14DAYS.md`
- Full API: `docs/API.md` (to be created)
- Architecture: See folder structure above

---

## 🔮 Future Roadmap (Post-MVP)

### Phase 2: Production Hardening (Month 2)
- Multi-organization support (Medellín, other cities)
- Advanced auth (roles, permissions)
- Drift monitoring & automated retraining
- SLA monitoring + PagerDuty alerts

### Phase 3: ML Improvements (Month 3)
- Ensemble models (XGBoost + RandomForest)
- Transfer learning from similar regions
- Real-time feature importance reporting
- Anomaly detection in data sources

### Phase 4: UX Enhancements (Month 4)
- Mobile app (React Native)
- Offline capability (progressive web app)
- Detailed risk explanations (SHAP values)
- Customizable alert thresholds by user

---

## 📝 Notes for Claude/Team

When working on this project:
1. **Keep all Python code under `platform/backend/` as one package** — never split shared modules across top-level folders
2. **Update CLAUDE.md** if architecture or key decisions change
3. **Prioritize P0 issues** (security) before features
4. **Test all scraper changes** against real data (not mock)
5. **Validate ML predictions** in staging before production
6. **Document rationale** for any threshold/constant changes

---

**Last Updated:** June 2026
**Maintainer:** Juan Pablo Botero
**Status:** Active Development (Post-Audit Phase)
