# TEYVA — Contexto del Proyecto

Plataforma de monitoreo de riesgo de deslizamientos para Medellín (19 comunas + corregimientos). MVP funcional: ingesta de datos en tiempo real, predicción ML a 7 días, API REST, dashboard web con IA conversacional y alertas Slack.

## Arquitectura

```
teyva/
├── platform/
│   ├── backend/          # ÚNICO paquete Python (PYTHONPATH apunta aquí)
│   │   ├── domain/       # Reglas PURAS (sin I/O): risk_rules.py (umbrales, categorías,
│   │   │                 #   compute_alert_state) + communes.py (fuente ÚNICA del territorio)
│   │   ├── application/  # Casos de uso: predict_risk.py, fire_alerts.py, train_model.py
│   │   ├── infrastructure/
│   │   │   ├── repositories/  # Queries compartidas (última predicción por comuna, etc.)
│   │   │   └── external/      # Clientes HTTP/SDK: arcgis, slack, osrm, llm
│   │   ├── ml/           # Motor ML: train.py, predict.py (inferencia), benchmark.py, models/
│   │   ├── scraper/      # siata (30min), dagrd (1h), ideam (6h), medellin_datos (24h), sismos
│   │   │   └── scheduler.py  # APScheduler daemon + watchdog de salud (alerta Slack)
│   │   ├── db/           # SQLAlchemy async+sync, session.py, 12+ tablas
│   │   ├── api/          # FastAPI: routes/ + auth.py (roles) + rate_limit.py + audit.py
│   │   ├── agent/        # Chat: Claude (primario) + Ollama (fallback), RAG, MCP
│   │   ├── rag/          # ChromaDB + sentence-transformers (2,127 chunks)
│   │   ├── alerts/       # Construcción de alertas Slack + Snake Line + evacuación
│   │   ├── constants.py  # SOLO config operativa: cooldowns, intervalos de scrapers
│   │   └── alembic/      # migraciones (7+)
│   └── frontend/         # Next.js 16 + React 19 + Tailwind 4 + Radix/shadcn
│       ├── components/dashboard/  # mapa, KPIs, chat, historial, monitor lluvia, salud
│       └── lib/api.ts    # cliente fetch centralizado
├── .github/workflows/    # 6 crons: 5 scrapers + predict-risk (corren alembic + escriben a Supabase)
└── docker-compose.yml    # stack local: db (fallback), ollama, backend, frontend, scraper, ml
```

**Regla de oro:** todo el Python vive bajo `platform/backend/` como UN paquete — los módulos se importan como top-level (`from domain.communes...`, `from db.models...`). No separar en carpetas raíz distintas: rompe imports y workflows.

**Capas (dirección de dependencias `api/scraper → application → domain/infrastructure`):**
- `domain/` no importa NADA con I/O. `domain/communes.py` es la única definición del territorio: id canónico ("1".."21", el de los DATOS) vs código oficial ("01".."16", "50".."90", solo para ArcGIS/cartografía). Cualquier lista de comunas nueva = bug.
- Los **entrypoints que invoca GitHub Actions NO se mueven** (`python -m scraper.siata`, `python -m ml.predict`, `python -m ml.train`): son wrappers finos que delegan a `application/`.
- La composición de alertas (qué checks corren tras ingesta/predicción/periódico) vive SOLO en `application/fire_alerts.py`.

## Base de datos — UNA sola fuente de verdad

**Supabase (PostgreSQL) vía Connection Pooler** es la BD de todo: GitHub Actions, Docker local y desarrollo a mano.

- Conexión SIEMPRE por el pooler (`aws-1-us-west-2.pooler.supabase.com:5432`, Session mode): el host directo `db.<ref>.supabase.co` es **IPv6-only** y no resuelve en la mayoría de redes locales.
- `DB_SSL=true` obligatorio. asyncpg usa contexto TLS sin verificación de cert (Supabase firma con CA propia) — equivalente a `sslmode=require`; ya resuelto en `db/session.py`.
- El `db` de docker-compose es solo **fallback offline** (si el `.env` raíz no define `DATABASE_URL`).
- Esquema: gestionado por Alembic. **Nunca editar migraciones ya aplicadas** — eso causó drift real entre Supabase y local. Cambio de esquema = migración nueva.
- **Aplicar migraciones SOLO desde `main` ya pusheado.** Aplicar a Supabase y commitear después deja `alembic_version` apuntando a una revisión que el repo no conoce, y los 6 crons fallan con `Can't locate revision` (pasó el 2026-07-26). Guard: `python -m monitoring.migration_guard --json`; runbook en `docs/RUNBOOK_MIGRATIONS.md`. Los crons ya no mueren por esto — `.github/actions/db-migrate` omite el upgrade y sigue ingiriendo — pero el drift bloquea toda migración nueva hasta resolverlo.

## Cómo correr

```bash
docker compose up            # stack completo → http://localhost:3000

# Backend a mano:
cd platform/backend && export PYTHONPATH=.
uvicorn api.main:app --reload --port 8000
python -m ml.predict         # predicciones batch
python -m scraper.scheduler  # daemon scrapers + watchdog
alembic upgrade head         # migraciones

# Frontend a mano:
cd platform/frontend && pnpm dev
```

## Datos y ML

- **Fuentes:** SIATA (lluvia), IDEAM (meteorología), DAGRD (emergencias), GeoMedellín (features geográficas). Los scrapers deduplican por `source_row_id` — `records_valid=0` con status `ok` significa "sin eventos NUEVOS", no error.
- **Modelo:** XGBoost. AUC-ROC 0.944, recall 0.999 (conservador). SMOTE para desbalance (26 positivos / 8,429 muestras).
- **Gobernanza del pipeline ML** (`ml/train.py`): los 4 artefactos (`best_model.pkl`, `scaler.pkl`, `feature_names.json`, `metrics.json`) se escriben JUNTOS y solo si el entrenamiento completa; una corrida abortada escribe `last_train_attempt.json` (gitignored) y NO toca producción. `metrics.json` lleva `trained_at` + `git_commit_sha`. Métricas extra: `train_auc_temporal` (validación pasado→futuro) y `benchmark_auc` (snapshot fijo en `ml/models/benchmark.json`, congelar con `python -m ml.benchmark --freeze`).
- **Eventos sintéticos:** `landslide_events.is_synthetic=true` (144, generados por `scraper/ingest_synthetic_events.py` con Snake Line) sirven para calibrar Snake Line y están EXCLUIDOS del training del clasificador — entrenar y validar con la misma heurística es contaminación circular. El filtro vive en `infrastructure/repositories/landslide_events.py`.
- **Umbrales riesgo:** SOLO en `domain/risk_rules.py` (`risk_level_from_score`): medio 0.35 / alto 0.65 / crítico 0.90. Categorías se guardan en minúscula sin tilde (`critico`); presentación vía `display_label()`.

## Chat + RAG

`LLM_PROVIDER=anthropic` (default, `claude-haiku-4-5`) con fallback automático a Ollama (`llama3.2`). Ambos comparten prompt y las 5 tools de `agent/rag_tools.py`. RAG en ChromaDB con citas de fuentes automáticas (contextvars). `ENABLE_RAG=true` lo activa. El historial de conversaciones se sirve en `GET /api/chat/sessions` (agrega `agent_conversations`, sin tabla extra).

## Seguridad

- Endpoints mutantes (`/predict-all`, `/predict-commune`, `PUT /rain/thresholds`, `GET|POST /rain/settings/webhook*`, `POST /alerts/report`) exigen `Authorization: Bearer $API_TOKEN` (`api/auth.py`, con rol `viewer` opcional vía `API_TOKEN_VIEWER`).
- **`ENV=production` sin `API_TOKEN` = el backend NO ARRANCA** (`assert_production_auth`). Sin token en dev = permite todo con warning.
- Rate limiting in-memory por IP (`api/rate_limit.py`): chat 10 req/min, predict 5 req/min. Si se escala a varios workers, migrar a Redis.
- Auditoría append-only en tabla `audit_log` (`api/audit.py::log_audit_event`): umbrales, webhooks, predicciones manuales, reportes. Se guarda hash SHA-256 del payload, nunca el payload crudo.
- Los `load_dotenv` usan `override=False`: el entorno real SIEMPRE gana sobre `.env` (un `API_TOKEN=` vacío en `.env` llegó a pisar el token real).
- CORS restringido vía `ALLOWED_ORIGINS`.
- **Jamás** commitear secretos: `.env` está en gitignore; `.env.example` solo placeholders. (Ya hubo una password real filtrada en el historial — rotada. No repetir.)

## Alertas y monitoreo

`alerts/slack.py` — 3 tipos con cooldown en `app_settings`: lluvia sobre umbral, riesgo crítico, y **scrapers caídos** (fallos consecutivos O staleness — silencio > 3× intervalo, cubre el caso "GitHub Actions se deshabilitó solo"). El watchdog corre en el scheduler cada 30 min. Webhook: env `SLACK_WEBHOOK_URL` o UI (BD).

Agentes en `monitoring/` (resultado → `agent_run_logs`, Slack vía `notify.py`): `api_health`, `ml_drift`, `scraper_validator` y `migration_guard` (drift Alembic BD↔repo). **Regla anti-ruido:** en estado `ok` se usa `log_agent_run`, NUNCA `fire_agent_alert` — este último postea a Slack siempre, y con agentes que corren cada 15–30 min eso ahoga las alertas reales. Se avisa al caer y al recuperarse.

Todo workflow fallido avisa a Slack vía `.github/actions/notify-failure` (bash+curl puro: funciona aunque haya fallado `pip install`; solo notifica la transición ok→fallo).

**Gotcha conocido:** GitHub deshabilita los crons tras 60 días sin commits (`disabled_inactivity`). Si las fuentes se ven caídas, revisar `gh workflow list` primero.

## Convenciones

- Python: type hints obligatorios, async para I/O, snake_case. TypeScript: strict, camelCase, componentes PascalCase, estilos Tailwind + tokens en `app/globals.css`.
- Tests de prompts: `/eval-prompt chat_rag|risk_explanations|slack_webhooks` (reportes en `tests/eval_results/`).
- No testear solo el happy path; scrapers se prueban contra datos reales.
- Actualizar este archivo si cambia la arquitectura.

## Contacto

Owner: Juan Pablo Botero (jbotero@aztia.co) · Stakeholder: Gestión del Riesgo Medellín

**Última actualización:** Julio 2026 (refactor por capas domain/application/infrastructure)
