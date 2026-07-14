# Especificación de la API — TEYVA

API REST construida con FastAPI. Documentación interactiva disponible en `http://localhost:8000/docs` (Swagger UI) y `http://localhost:8000/redoc`.

**Base URL:** `http://localhost:8000`  
**Autenticación:** Bearer token en header `Authorization: Bearer <API_TOKEN>` (requerido en endpoints mutantes)

---

## Endpoints de Riesgo

### `GET /api/risk/comunas`
Retorna el nivel de riesgo actual de todas las comunas.

**Respuesta 200:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "commune_id": "13",
        "nombre": "San Javier",
        "risk_score": 0.72,
        "risk_category": "alto",
        "last_prediction": "2026-07-13T14:30:00Z"
      },
      "geometry": { "type": "Polygon", "coordinates": [[...]] }
    }
  ]
}
```

---

### `GET /api/risk/comuna/{commune_id}/detalle`
Detalle completo de una comuna: riesgo, lluvia reciente, eventos y recomendación.

**Parámetros:**
- `commune_id` (path) — ID de la comuna ("1"–"21")

**Respuesta 200:**
```json
{
  "commune_id": "13",
  "nombre": "San Javier",
  "risk_score": 0.72,
  "risk_category": "alto",
  "risk_label": "Alto",
  "precip_24h_mm": 45.3,
  "precip_7d_mm": 182.1,
  "n_events_30d": 3,
  "recommendation": "Activar protocolos preventivos. Monitorear quebradas y taludes.",
  "last_updated": "2026-07-13T14:30:00Z"
}
```

---

### `GET /api/risk/historia/{commune_id}`
Serie temporal de predicciones de riesgo de los últimos 30 días.

**Respuesta 200:**
```json
{
  "commune_id": "13",
  "history": [
    { "date": "2026-07-13", "risk_score": 0.72, "risk_category": "alto" },
    { "date": "2026-07-12", "risk_score": 0.61, "risk_category": "medio" }
  ]
}
```

---

### `POST /api/risk/predict-all` 🔒
Dispara predicción batch para todas las comunas.

**Headers:** `Authorization: Bearer <API_TOKEN>`  
**Respuesta 200:** `{ "status": "ok", "comunas_updated": 21 }`

---

### `POST /api/risk/predict-commune` 🔒
Predicción on-demand para una sola comuna.

**Body:**
```json
{ "commune_id": "13" }
```

---

## Endpoints de Lluvia

### `GET /api/rain/timeseries/{commune_id}`
Serie temporal de precipitación de los últimos N días.

**Query params:** `days` (int, default 7, max 90)

**Respuesta 200:**
```json
{
  "commune_id": "13",
  "days": 7,
  "total_mm": 182.1,
  "peak_mm": 38.5,
  "readings": [
    { "snapshot_at": "2026-07-13T14:00:00Z", "precip_mm": 12.3 }
  ]
}
```

---

### `GET /api/rain/settings` 🔒
Obtiene los umbrales de alerta de lluvia configurados.

### `PUT /api/rain/thresholds` 🔒
Actualiza umbrales de alerta de lluvia.

---

## Endpoints de Chat

### `POST /api/chat`
Envía un mensaje al agente conversacional TEYVA.

**Body:**
```json
{
  "message": "¿Qué comunas debo vigilar esta semana?",
  "session_id": "uuid-opcional"
}
```

**Respuesta 200 (streaming):**
```json
{
  "response": "Esta semana te recomiendo estar muy pendiente de San Javier y Manrique...",
  "session_id": "a1b2c3d4-...",
  "sources": ["Reporte semanal SIATA HIDROMET (2026-07-07)"]
}
```

---

### `GET /api/chat/sessions`
Lista las sesiones de conversación con sus resúmenes.

### `GET /api/chat/sessions/{session_id}`
Historial completo de una sesión de chat.

---

## Endpoints de Alertas

### `GET /api/alerts/active`
Alertas activas en este momento.

### `POST /api/alerts/report` 🔒
Registra un reporte de incidente (uso interno del agente).

---

## Endpoints de Monitoreo

### `GET /api/scraper/status`
Estado de salud de los scrapers (última ejecución, registros válidos).

### `GET /api/health`
Health check general del sistema.

**Respuesta 200:** `{ "status": "ok", "db": "ok", "llm": "anthropic", "rag": true }`

---

## Endpoints de Auditoría

### `GET /api/audit/log` 🔒
Log de auditoría (umbrales cambiados, predicciones manuales, reportes).

---

## Códigos de error

| Código | Significado |
|---|---|
| `400` | Parámetros inválidos |
| `401` | Token ausente o inválido |
| `404` | Recurso no encontrado |
| `429` | Rate limit excedido (chat: 10 req/min, predict: 5 req/min) |
| `500` | Error interno del servidor |
| `503` | Servicio dependiente no disponible (LLM, BD) |
