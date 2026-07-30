# API

FastAPI app (`platform/backend/api/main.py`). Routers and prefixes:

| Router | Prefix |
|---|---|
| `routes/risk.py` | `/api/risk` |
| `routes/chat.py` | `/api/chat` |
| `routes/scraper.py` | `/api/scraper` |
| `routes/rain.py` | `/api/rain` |
| `routes/alerts.py` | `/api/alerts` |

**Auth.** Mutating endpoints require `Authorization: Bearer $API_TOKEN`
(`api/auth.py::require_token`). Everything else is open (read-only, GET). In `ENV=production`
without `API_TOKEN` set, the backend refuses to start. Some endpoints also carry per-IP/session
rate limits (`api/rate_limit.py`).

Endpoints below were extracted directly from the route source; response shapes are simplified
examples based on the actual code, not fabricated schemas.

## Risk (`/api/risk`)

| Method & path | Purpose | Auth |
|---|---|---|
| `GET /predictions/latest?limit=50` | Latest N risk predictions across all communes | none |
| `GET /comunas` | GeoJSON FeatureCollection, one feature per commune with current risk | none |
| `GET /comuna/{commune_id}` | Latest risk summary for one commune | none |
| `GET /comuna/{commune_id}/detalle` | Full detail: risk, 7d/30d rainfall, recent events, explanation | none |
| `GET /derivation/{commune_id}` | Neuro-symbolic derivation (fired rules, conflicts, confidence) | none |
| `GET /barrios-hazard` | Official geomorphological hazard grade per barrio (~401 polygons) | none |
| `GET /seismic-events?days=365` | Deduplicated recent earthquakes (SIATA network) | none |
| `GET /mesh-grid` | ~1.5km grid cells (JMA Mesh Maps), risk inherited from commune | none |
| `GET /mesh-grid/{quad_id}` | One grid cell + inherited risk | none |
| `GET /snake-line/{commune_id}` | Snake Line point + 48h history (SWI × heavy rain) | none |
| `GET /soil-water-index` | Estimated soil saturation % per commune | none |
| `GET /alert-state/{commune_id}` | Composite Green/Yellow/Red state for one commune | none |
| `GET /alert-state` | Composite state for all 21 communes | none |
| `GET /explanation/{commune_id}` | Latest AI-generated narrative explanation | none |
| `GET /historia/{commune_id}` | 30-day daily series: rainfall, landslides, risk | none |
| `GET /estadisticas` | Dashboard KPIs (communes at critical/high risk, 30d events, trend) | none |
| `GET /alerts` | Top 10 active alerts (communes in alto/critico, last 7 days) | none |
| `POST /predict-all` | Run predictions for all 21 communes | **Bearer token**, 5 req/min |
| `POST /predict-commune` | Run prediction for one commune | **Bearer token**, 5 req/min |
| `GET /observability/predictions?limit=100` | Recent prediction logs for drift monitoring | none |

```bash
curl http://localhost:8000/api/risk/comuna/1/detalle
```
```json
{
  "commune_id": "1",
  "nombre_comuna": "Popular",
  "risk_score": 0.42,
  "risk_category": "medio",
  "created_at": "2026-07-30T06:00:00+00:00",
  "rainfall_last_7d_daily": [{"date": "2026-07-24", "rainfall": 12.4}],
  "rainfall_last_7d_total": 58.3,
  "rainfall_last_30d_total": 210.1,
  "historical_events": [{"id": 101, "fecha": "2026-05-02", "tipo_emergencia": "deslizamiento", "barrio": "Santo Domingo"}],
  "is_zona_ladera": true,
  "model_explanation": "...",
  "predicted_at": "2026-07-30T06:00:00+00:00",
  "derivation": null
}
```

```bash
curl -X POST http://localhost:8000/api/risk/predict-commune \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"commune_id": "1"}'
```

## Chat (`/api/chat`)

| Method & path | Purpose | Auth |
|---|---|---|
| `POST /` or `POST /message` | Send a chat message, get a full reply | none, 10 req/min per IP + per session |
| `POST /stream` | Same, streamed as SSE (`data: {"chunk": ...}` events, ends `[DONE]`) | none, same rate limit |
| `GET /sessions?limit=50&offset=0&q=` | List conversation sessions (title/preview aggregated from `agent_conversations`) | none |
| `GET /history/{session_id}?limit=40` | Full message history for a session | none |

```bash
curl -X POST http://localhost:8000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Cuál es el riesgo en la comuna 1?", "session_id": "abc-123"}'
```
```json
{"reply": "La comuna 1 (Popular) tiene riesgo medio...", "session_id": "abc-123"}
```

## Scraper (`/api/scraper`)

| Method & path | Purpose | Auth |
|---|---|---|
| `POST /log` | Record a scrape run (source, status, detail) | none |
| `GET /logs?limit=30` | Recent scrape logs | none |
| `GET /status` | Per-source totals (downloaded/valid/discarded) | none |
| `GET /health` | Per-source health classification (healthy/warning/critical/unknown) | none |
| `GET /timeline` | Last 20 runs per source | none |

```bash
curl http://localhost:8000/api/scraper/health
```
```json
{"overall": "healthy", "sources": [{"source": "siata", "status": "healthy", "consecutive_failures": 0, "data_lag_minutes": 12}], "computed_at": "2026-07-30T12:00:00+00:00"}
```

## Rain (`/api/rain`)

| Method & path | Purpose | Auth |
|---|---|---|
| `GET /live` | Today's SIATA rain snapshots + running accumulation per commune | none |
| `GET /spearman` | Spearman correlation between rainfall and landslide event counts | none |
| `GET /thresholds` | Per-commune daily rain threshold (mm) | none |
| `PUT /thresholds/{commune_id}` | Set a commune's threshold (`{"threshold_mm": 35.0}`) | **Bearer token** |
| `GET /settings/webhook` | Whether a Slack webhook is configured (masked URL) | **Bearer token** |
| `POST /settings/webhook` | Save the Slack webhook URL (`{"url": "https://..."}`) | **Bearer token** |
| `POST /settings/webhook/test` | Fire a test Slack message | **Bearer token** |
| `GET /alerts/log` | Last 50 rain-alert log entries | none |

```bash
curl -X PUT http://localhost:8000/api/rain/thresholds/1 \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"threshold_mm": 40.0}'
```

## Alerts (`/api/alerts`)

| Method & path | Purpose | Auth |
|---|---|---|
| `GET /chart/{commune_id}?days=7` | Rain PNG chart with threshold/peak markers | none |
| `GET /evacuation-routes/{commune_id}` | Nearest OSM safe zones + walking route (MVP, not validated by DAGRD) | none |
| `POST /report?send_to_slack=false` | Generate the valley's plain-language situation report (≤200 words) | **Bearer token** |

```bash
curl -X POST "http://localhost:8000/api/alerts/report?send_to_slack=true" \
  -H "Authorization: Bearer $API_TOKEN"
```
```json
{"report": "Situación general del valle...", "slack_sent": true}
```

## Notes / caveats

- Response examples above are illustrative, built from the actual route/model code, not live
  API responses — verify shapes against the live OpenAPI docs at `/docs` if you need exact field
  guarantees.
- Audit logging (`api/audit.py`) records a hash of the payload — never the raw payload — for
  every token-gated mutating call.
