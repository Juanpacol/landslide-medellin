# Changelog — TEYVA

Todos los cambios relevantes del proyecto están documentados aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).

---

## [1.2.0] — 2026-07-13

### Añadido
- Agente conversacional con RAG: tool-calling sobre ChromaDB (2,127 chunks de SIATA, DAGRD y perfiles de comunas).
- 8 herramientas del agente: predicciones, lluvia, eventos, evacuación, reporte ciudadano, situación general, salud de scrapers y búsqueda semántica.
- Explicaciones automáticas de riesgo por comuna generadas con Claude (JSON estructurado).
- Rutas de evacuación via OpenStreetMap + OSRM.
- Canal de reportes ciudadanos (`citizen_reports`, tabla separada de eventos oficiales).
- Auditoría append-only con hash SHA-256 del payload.
- Rate limiting por IP: chat 10 req/min, predicción 5 req/min.
- Watchdog de scrapers: alerta Slack si una fuente lleva >3× su intervalo sin datos.
- Sistema de diseño completo: paleta tierra OKLCH, Bricolage Grotesque + Hanken Grotesk.
- Refactor por capas: `domain/` → `application/` → `infrastructure/`.

### Cambiado
- LLM primario migrado a Claude Haiku 4-5 (Anthropic); Ollama como fallback automático.
- `communes.py` como única fuente de verdad del territorio (21 comunas + corregimientos).
- Alertas Slack mejoradas: sparkline ASCII + botón "Ver gráfica" cuando no hay bot token.

### Corregido
- Drift de esquema entre Supabase y local (migraciones nunca se editan, solo se añaden nuevas).
- `load_dotenv` con `override=False` para que el entorno real gane sobre `.env`.

---

## [1.1.0] — 2026-04-10

### Añadido
- Predicción de riesgo a 7 días con XGBoost + SMOTE (AUC-ROC 0.944, Recall 0.999).
- Validación temporal pasado→futuro (`train_auc_temporal`) y benchmark fijo (`benchmark_auc`).
- Scrapers: SIATA (30 min), DAGRD (1 h), IDEAM (6 h), GeoMedellín (24 h), sismos.
- 6 workflows GitHub Actions: 5 scrapers + predict-risk (corren Alembic + escriben a Supabase).
- Alertas Slack: lluvia sobre umbral y riesgo crítico con cooldowns configurables.
- Dashboard Next.js 16 + React 19 + Tailwind 4: mapa de riesgo, KPIs, gráfico de precipitación.
- Historial de conversaciones en `agent_conversations`.

### Cambiado
- Base de datos migrada de Neon a Supabase (Connection Pooler, Session mode).
- Eventos sintéticos (144, Snake Line) excluidos del entrenamiento para evitar contaminación circular.

---

## [1.0.0] — 2026-01-15

### Añadido
- MVP inicial: scraper básico SIATA + modelo RandomForest + API FastAPI + chat Ollama.
- Esquema inicial con Alembic (`b791d657baae_initial_schema.py`).
- Docker Compose con stack completo: DB, Ollama, backend, frontend.
