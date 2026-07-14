# Arquitectura del Sistema — TEYVA

Esta carpeta contiene los diagramas de arquitectura del sistema.

---

## Diagrama de arquitectura general

```
┌─────────────────────────────────────────────────────────────────┐
│                        FUENTES DE DATOS                         │
│   SIATA (30min)  │  DAGRD (1h)  │  IDEAM (6h)  │  GeoMed (24h) │
└────────┬─────────┴──────┬───────┴──────┬────────┴───────┬───────┘
         │                │              │                │
         └────────────────┴──────┬───────┘                │
                                 │ Scrapers (APScheduler)  │
                                 ▼                        │
                    ┌────────────────────┐                │
                    │  PostgreSQL        │ ◄──────────────┘
                    │  (Supabase)        │   ArcGIS Client
                    │                   │
                    │  ml_features       │
                    │  landslide_events  │
                    │  risk_predictions  │
                    │  rainfall_ts       │
                    │  scraping_logs     │
                    │  citizen_reports   │
                    └─────────┬──────────┘
                              │
               ┌──────────────┼──────────────┐
               ▼              ▼              ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │   ML Engine  │  │  ChromaDB    │  │  FastAPI     │
    │  (XGBoost)   │  │  (RAG 2127   │  │  REST API    │
    │              │  │   chunks)    │  │              │
    │  AUC: 0.944  │  │  embeddings  │  │  /api/risk   │
    │  Recall:0.999│  │  multilingual│  │  /api/chat   │
    └──────┬───────┘  └──────┬───────┘  │  /api/rain   │
           │                 │          │  /api/alerts │
           └────────┬────────┘          └──────┬───────┘
                    ▼                          │
         ┌──────────────────┐                 │
         │  Agente TEYVA    │ ◄───────────────┘
         │                  │
         │  Claude H. 4-5   │  ← primario
         │  Ollama fallback  │  ← offline/backup
         │  8 tools          │
         └────────┬─────────┘
                  │
     ┌────────────┴────────────┐
     ▼                         ▼
┌─────────────┐         ┌─────────────┐
│  Dashboard  │         │  Slack      │
│  Next.js 16 │         │  Alertas    │
│  React 19   │         │  (webhook)  │
│  Leaflet    │         └─────────────┘
│  Tailwind 4 │
└─────────────┘
```

---

## Capas de la aplicación (dirección de dependencias)

```
api/ scraper/ agent/
       │
       ▼
  application/          ← casos de uso: predict_risk, fire_alerts, train_model
       │
  ┌────┴────┐
  ▼         ▼
domain/   infrastructure/   ← repositorios, clientes externos
(sin I/O)  (I/O: DB, HTTP)
```

**Regla:** `domain/` no importa nada con I/O. Cualquier lógica que necesite acceder a la BD o a servicios externos va en `infrastructure/` o `application/`.

---

## Flujo de predicción

```
1. GitHub Actions activa el cron de predict-risk (cada N horas)
2. Se aplican migraciones: alembic upgrade head
3. python -m ml.predict:
   a. Lee ml_features de las últimas 24h por comuna
   b. Carga best_model.pkl + scaler.pkl + feature_names.json
   c. Genera risk_score para cada una de las 21 comunas
   d. Clasifica: bajo/medio/alto/crítico
   e. Inserta en risk_predictions
4. application/fire_alerts.py evalúa si disparar alertas Slack
5. El dashboard Next.js consume /api/risk/comunas en tiempo real
```

---

## Flujo del agente conversacional

```
Usuario → POST /api/chat {message, session_id}
  │
  ├─ agent/chat_rag.py inicializa contexto (fuentes, session)
  │
  ├─ Loop tool-calling (máx. RAG_MAX_TOOL_ROUNDS=3):
  │   ├─ Claude recibe system_prompt + historial + mensaje
  │   ├─ Claude decide qué tool(s) llamar
  │   ├─ Se ejecutan las tools (consultas a BD + ChromaDB)
  │   └─ Resultados se devuelven al modelo
  │
  ├─ Claude genera respuesta final en lenguaje natural
  ├─ Se agregan citas de fuentes (ChromaDB → PDF/URL)
  └─ Se guarda en agent_conversations + se retorna al usuario
```

---

## Archivos de diagrama

- `architecture_overview.png` — Diagrama visual de la arquitectura (pendiente de exportar)
- `data_flow.png` — Flujo de datos de extremo a extremo (pendiente de exportar)
- `ml_pipeline.png` — Pipeline de entrenamiento e inferencia (pendiente de exportar)
