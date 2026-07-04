# TEYVA — Contexto del Proyecto

Plataforma de monitoreo de riesgo de deslizamientos para Medellín (19 comunas + corregimientos). MVP funcional: ingesta de datos en tiempo real, predicción ML a 7 días, API REST, dashboard web con IA conversacional y alertas Slack.

## Arquitectura

```
teyva/
├── platform/
│   ├── backend/          # ÚNICO paquete Python (PYTHONPATH apunta aquí)
│   │   ├── ml/           # XGBoost: train.py, predict.py, features.py, models/ (artefactos)
│   │   ├── scraper/      # siata (30min), dagrd (1h), ideam (6h), medellin_datos (24h)
│   │   │   └── scheduler.py  # APScheduler daemon + watchdog de salud (alerta Slack)
│   │   ├── db/           # SQLAlchemy async+sync, 10 tablas, session.py
│   │   ├── api/          # FastAPI: routes/ (risk, chat, scraper, rain, alerts) + auth.py
│   │   ├── agent/        # Chat: Claude (primario) + Ollama (fallback), RAG, MCP
│   │   ├── rag/          # ChromaDB + sentence-transformers (2,127 chunks)
│   │   ├── alerts/       # Slack: lluvia, riesgo crítico, scrapers caídos
│   │   ├── constants.py  # Fuente única: umbrales de riesgo, intervalos de scrapers
│   │   └── alembic/      # 4 migraciones
│   └── frontend/         # Next.js 16 + React 19 + Tailwind 4 + Radix/shadcn
│       ├── components/dashboard/  # mapa, KPIs, chat, historial, monitor lluvia, salud
│       └── lib/api.ts    # cliente fetch centralizado
├── .github/workflows/    # 5 crons: 4 scrapers + predict-risk (escriben a Supabase)
└── docker-compose.yml    # stack local: db (fallback), ollama, backend, frontend, scraper, ml
```

**Regla de oro:** todo el Python vive bajo `platform/backend/` como UN paquete — los módulos se importan como top-level (`from db.models...`, `from scraper.common...`). No separar en carpetas raíz distintas: rompe imports y workflows.

## Base de datos — UNA sola fuente de verdad

**Supabase (PostgreSQL) vía Connection Pooler** es la BD de todo: GitHub Actions, Docker local y desarrollo a mano.

- Conexión SIEMPRE por el pooler (`aws-1-us-west-2.pooler.supabase.com:5432`, Session mode): el host directo `db.<ref>.supabase.co` es **IPv6-only** y no resuelve en la mayoría de redes locales.
- `DB_SSL=true` obligatorio. asyncpg usa contexto TLS sin verificación de cert (Supabase firma con CA propia) — equivalente a `sslmode=require`; ya resuelto en `db/session.py`.
- El `db` de docker-compose es solo **fallback offline** (si el `.env` raíz no define `DATABASE_URL`).
- Esquema: gestionado por Alembic. **Nunca editar migraciones ya aplicadas** — eso causó drift real entre Supabase y local. Cambio de esquema = migración nueva.

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
- **Umbrales riesgo:** SOLO en `constants.py` (`risk_level_from_score`): medio 0.35 / alto 0.65 / crítico 0.90. Categorías se guardan en minúscula sin tilde (`critico`); presentación vía `display_label()`.

## Chat + RAG

`LLM_PROVIDER=anthropic` (default, `claude-haiku-4-5`) con fallback automático a Ollama (`llama3.2`). Ambos comparten prompt y las 5 tools de `agent/rag_tools.py`. RAG en ChromaDB con citas de fuentes automáticas (contextvars). `ENABLE_RAG=true` lo activa. El historial de conversaciones se sirve en `GET /api/chat/sessions` (agrega `agent_conversations`, sin tabla extra).

## Seguridad

- Endpoints mutantes (`/predict-all`, `/predict-commune`, `PUT /rain/thresholds`, `POST /rain/settings/webhook*`) exigen `Authorization: Bearer $API_TOKEN` (`api/auth.py`). Sin `API_TOKEN` definido = modo dev (permite todo con warning).
- CORS restringido vía `ALLOWED_ORIGINS`.
- **Jamás** commitear secretos: `.env` está en gitignore; `.env.example` solo placeholders. (Ya hubo una password real filtrada en el historial — rotada. No repetir.)

## Alertas y monitoreo

`alerts/slack.py` — 3 tipos con cooldown en `app_settings`: lluvia sobre umbral, riesgo crítico, y **scrapers caídos** (fallos consecutivos O staleness — silencio > 3× intervalo, cubre el caso "GitHub Actions se deshabilitó solo"). El watchdog corre en el scheduler cada 30 min. Webhook: env `SLACK_WEBHOOK_URL` o UI (BD).

**Gotcha conocido:** GitHub deshabilita los crons tras 60 días sin commits (`disabled_inactivity`). Si las fuentes se ven caídas, revisar `gh workflow list` primero.

## Convenciones

- Python: type hints obligatorios, async para I/O, snake_case. TypeScript: strict, camelCase, componentes PascalCase, estilos Tailwind + tokens en `app/globals.css`.
- Tests de prompts: `/eval-prompt chat_rag|risk_explanations|slack_webhooks` (reportes en `tests/eval_results/`).
- No testear solo el happy path; scrapers se prueban contra datos reales.
- Actualizar este archivo si cambia la arquitectura.

## Contacto

Owner: Juan Pablo Botero (jbotero@aztia.co) · Stakeholder: Gestión del Riesgo Medellín

**Última actualización:** Julio 2026
