# TEYVA MVP

Plataforma para monitorear y estimar riesgo de deslizamientos en Medellin, integrando datos reales, modelo predictivo, API, dashboard web y asistente conversacional con Ollama.

## Que resuelve

TEYVA centraliza informacion que normalmente esta dispersa (lluvia, eventos historicos, contexto territorial) para responder dos preguntas operativas:

- Que zonas tienen mayor riesgo hoy.
- Como comunicar ese riesgo de forma clara a equipos no tecnicos.

## Arquitectura general

El MVP se divide en 4 bloques:

1. Scraper: recolecta y normaliza datos de fuentes externas.
2. ML: construye features, entrena modelo y genera predicciones.
3. API: expone los datos y resultados para consumo interno/externo.
4. Frontend + Chat: visualiza el estado de riesgo y permite consultas en lenguaje natural.

Flujo real de punta a punta:

`Fuentes externas -> Scraper -> Base de datos -> ML (entrenamiento/prediccion) -> API -> Dashboard y Chat`

## Stack usado (y para que)

### Backend
- FastAPI + Uvicorn: exponer endpoints REST de riesgo, estadisticas, historial y chat.
- SQLAlchemy (async/sync): acceso a base de datos desde API, ML y scraper.
- Alembic: control de migraciones de esquema.
- APScheduler: corridas periodicas del scraper.
- httpx/requests/BeautifulSoup: consumo y parsing de fuentes externas.

### ML
- scikit-learn: pipeline de entrenamiento y evaluacion.
- XGBoost / RandomForest / LogisticRegression: candidatos de modelo.
- imbalanced-learn (SMOTE): balanceo de clases.
- joblib: serializacion de artefactos (`best_model.pkl`, scaler, metricas).

### Frontend
- Next.js + React: dashboard web.
- Leaflet + React Leaflet: mapa por comunas/corregimientos.
- Chart.js / Recharts: visualizaciones de series e indicadores.

### Conversacional
- Ollama local: LLM para responder preguntas del usuario con lenguaje natural.

## Modulos principales

### 1) Scraper (`backend/scraper`)

Se implementaron scrapers por fuente:

- `siata.py`
- `ideam.py`
- `dagrd.py`
- `medellin_datos.py`

Y se orquestaron con:

- `scheduler.py`: programa corridas periodicas (30 min, 1h, 6h, 24h segun fuente).
- `historical_backfill.py`: carga historica.
- `historical_incremental.py`: carga incremental.
- `geocode_events.py`: geocodifica y ayuda a asignar eventos a territorio.

Para trazabilidad se registran ejecuciones en `scraping_logs`.

## 2) Capa de datos (`backend/db`)

La persistencia se maneja con PostgreSQL y modelos SQLAlchemy. Tablas clave:

- `ml_features`: variables agregadas por comuna y fecha.
- `landslide_events`: eventos historicos de deslizamiento.
- `risk_predictions`: resultado de inferencia del modelo.
- `agent_conversations`: historial de chat.
- `scraping_logs`: log de corridas de ingesta.

Conexion central:

- `backend/db/session.py` (usa `DATABASE_URL` y `DATABASE_URL_SYNC` desde `backend/.env`).

## 3) Entrenamiento ML (`backend/ml/train.py`)

Proceso real:

1. Lee `MLFeature` y `LandslideEvent`.
2. Construye matriz supervisada por comuna/fecha.
3. Define objetivo principal de prediccion a 7 dias (con fallback si no hay positivos).
4. Estandariza variables con `StandardScaler`.
5. Aplica `SMOTE` para balancear clases.
6. Evalua candidatos (`RandomForest`, `XGBClassifier`, `LogisticRegression`) con validacion cruzada.
7. Escoge el mejor por AUC-ROC.
8. Entrena el modelo final y guarda artefactos en `backend/ml/models/`.

Artefactos generados:

- `best_model.pkl`
- `metrics.json`
- `feature_names.json`
- `scaler.pkl`
- `report.md`

## 4) Prediccion operativa (`backend/ml/predict.py`)

En inferencia:

- Carga el modelo entrenado.
- Construye vector de features actual por comuna.
- Calcula `risk_score` (probabilidad) y lo traduce a nivel (`bajo`, `medio`, `alto`, `critico`).
- Guarda resultados en `risk_predictions` (proceso masivo para comunas).

## 5) API (`backend/api`)

Archivo principal: `backend/api/main.py`

Routers:

- `routes/risk.py`
- `routes/chat.py`
- `routes/scraper.py`

Endpoints de riesgo mas usados:

- `GET /api/risk/comunas`
- `GET /api/risk/comuna/{id}/detalle`
- `GET /api/risk/historia/{id}`
- `GET /api/risk/estadisticas`
- `GET /api/risk/alerts`
- `POST /api/risk/predict-all`

Chat:

- `POST /api/chat`
- `GET /api/chat/history/{session_id}`

## 6) Como funciona el chat con Ollama (`backend/agent/chat.py`)

Cuando un usuario pregunta:

1. Se recibe mensaje y `session_id`.
2. Se guarda el turno y se consulta historial corto de conversacion.
3. Se detecta si el mensaje menciona comuna especifica.
4. Se consulta contexto real en BD (riesgo, eventos, lluvia, alertas).
5. Se construye prompt con datos actuales.
6. Se llama a Ollama (`OLLAMA_URL`, `OLLAMA_MODEL`) via `POST /api/chat` de Ollama.
7. Si falla el modelo principal, se usa modelo fallback.
8. Se guarda y retorna la respuesta final al usuario.

Resultado: el asistente responde con base en datos de TEYVA, no solo texto generico.

## 7) Frontend (`static`)

Vista principal:

- `app/page.tsx` -> renderiza dashboard.

Componentes clave:

- `components/dashboard/dashboard.tsx`
- `components/dashboard/medellin-map.tsx`
- `components/dashboard/kpi-cards.tsx`
- `components/dashboard/rainfall-chart.tsx`
- `components/dashboard/commune-info.tsx`
- `components/dashboard/teyva-chat.tsx`

Integracion con backend:

- `static/lib/api.ts` concentra llamadas.
- `static/next.config.mjs` hace rewrite de `/api/*` a `http://localhost:8000/api/*`.

## 8) Variables de entorno

Definir en `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://...
DATABASE_URL_SYNC=postgresql://...
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_FALLBACK_MODEL=qwen2.5:0.5b
```

## 9) Como correr el proyecto

## Backend (desde `backend/`)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload --port 8000
```

## Frontend (desde `static/`)

```bash
pnpm install
pnpm dev
```

## Entrenamiento y prediccion

Desde `backend/`:

```bash
python -m ml.train
python -m ml.predict
```

## Scheduler de scraping

Desde `backend/`:

```bash
python -m scraper.scheduler
```

## Estado del MVP

Fortalezas:

- Integracion end-to-end funcional (datos -> modelo -> API -> dashboard -> chat).
- Prediccion territorial consumible en tiempo real por interfaz.
- Conversacion guiada por datos reales del sistema.

Pendientes esperados de un MVP:

- Hardening de seguridad y autenticacion de endpoints sensibles.
- Mayor robustez operacional y observabilidad.
- Mejora continua de calidad de datos y validacion de modelo en produccion.

## Equipo y objetivo de entrega

Este primer MVP fue construido para demostrar factibilidad tecnica y valor operativo temprano: priorizar zonas, reducir tiempo de analisis y facilitar comunicacion entre perfiles tecnicos y no tecnicos.

