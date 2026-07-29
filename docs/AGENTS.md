# TEYVA — Contracts Between Agents

## Shared layer
- backend/db/session.py   → get_db(), async_engine, sync_engine
- backend/db/models/      → all SQLAlchemy models
- .env                    → DATABASE_URL, DATABASE_URL_SYNC, OLLAMA_URL, OLLAMA_MODEL

## Agent 1 (ML) produces
- predict_risk(comuna_id, db) → dict
- predict_all_comunas(db) → None
- backend/ml/models/best_model.pkl
- Table: risk_predictions

## Agent 2 (Agent) consumes
- predict_risk() from Agent 1
- Tables: risk_predictions, landslide_events, agent_conversations
- Produces: chat(message, session_id, db) → str
- LLM: local Ollama (OLLAMA_URL, OLLAMA_MODEL)

## Agent 3 (Scraper) feeds
- Tables: ml_features, landslide_events, scraping_logs

## Agent 4 (API) connects everything
- First task: alembic upgrade head
- Imports chat() from Agent 2
- Imports predict_all_comunas() from Agent 1
- Exposes REST API + chat widget

## Environment variables
DATABASE_URL=postgresql+asyncpg://...neon.tech/neondb?sslmode=require
DATABASE_URL_SYNC=postgresql://...neon.tech/neondb?sslmode=require
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
