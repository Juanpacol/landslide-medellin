# TEYVA — Contratos entre Agentes

## Capa compartida
- backend/db/session.py   → get_db(), async_engine, sync_engine
- backend/db/models/      → todos los modelos SQLAlchemy
- .env                    → DATABASE_URL, DATABASE_URL_SYNC, OLLAMA_URL, OLLAMA_MODEL

## Agente 1 (ML) produce
- predict_risk(comuna_id, db) → dict
- predict_all_comunas(db) → None
- backend/ml/models/best_model.pkl
- Tabla: risk_predictions

## Agente 2 (Agent) consume
- predict_risk() del Agente 1
- Tablas: risk_predictions, landslide_events, agent_conversations
- Produce: chat(message, session_id, db) → str
- LLM: Ollama local (OLLAMA_URL, OLLAMA_MODEL)

## Agente 3 (Scraper) alimenta
- Tablas: ml_features, landslide_events, scraping_logs

## Agente 4 (API) conecta todo
- Primera tarea: alembic upgrade head
- Importa chat() del Agente 2
- Importa predict_all_comunas() del Agente 1
- Expone REST API + widget de chat

## Variables de entorno
DATABASE_URL=postgresql+asyncpg://...neon.tech/neondb?sslmode=require
DATABASE_URL_SYNC=postgresql://...neon.tech/neondb?sslmode=require
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2