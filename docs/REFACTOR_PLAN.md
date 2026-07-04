# TEYVA Major Architectural Refactor Plan
## React → HTMX | FastAPI → Go API | Full Containerization

**Status:** PLANNING PHASE  
**Risk Level:** 🔴 HIGH  
**Effort:** 8-11 weeks (4-person team)  
**Go/No-Go Decision Point:** End of Week 1 PoC

---

## TABLE OF CONTENTS

1. [Pre-Refactor Checklist](#pre-refactor-checklist)
2. [Phase 0: Risk Mitigation & Preparation](#phase-0-risk-mitigation--preparation)
3. [Phase 1: Architecture Design & PoC](#phase-1-architecture-design--poc)
4. [Phase 2: Go API Development](#phase-2-go-api-development)
5. [Phase 3: Python Microservices Extraction](#phase-3-python-microservices-extraction)
6. [Phase 4: Frontend Refactor (React → HTMX)](#phase-4-frontend-refactor-react--htmx)
7. [Phase 5: Containerization & Orchestration](#phase-5-containerization--orchestration)
8. [Phase 6: Integration Testing](#phase-6-integration-testing)
9. [Rollback Procedures](#rollback-procedures)
10. [Success Metrics](#success-metrics)

---

## PRE-REFACTOR CHECKLIST

**DO NOT SKIP THESE STEPS** - They prevent catastrophic failures:

- [ ] **Full code freeze** - No features merged during refactor
- [ ] **Current branch backup** - `git tag -a v1.0-pre-refactor "Before major refactor"`
- [ ] **Database snapshot** - Export full PostgreSQL dump to S3/backup
- [ ] **Performance baseline** - Document current response times:
  - [ ] API latency (p50, p95, p99)
  - [ ] Dashboard load time
  - [ ] Chat response time
  - [ ] Scraper job durations
- [ ] **User communication** - Notify stakeholders: "System unavailable weeks 2-4 for upgrade"
- [ ] **Incident response plan** - Who handles emergencies? What's the abort trigger?
- [ ] **Team skill verification**:
  - [ ] At least 1 senior Go developer (not learning Go during refactor)
  - [ ] At least 1 senior frontend dev (HTMX + Vanilla JS)
  - [ ] At least 1 DevOps engineer (Docker/Compose/K8s)
- [ ] **Tool setup**:
  - [ ] Go 1.21+ installed locally
  - [ ] Docker Desktop + Docker Compose 2.20+
  - [ ] New branch: `feature/refactor-architecture`

---

## PHASE 0: RISK MITIGATION & PREPARATION
**Duration:** 3-5 days (Week 0-1)

### 0.1 Extract Current Behavior as Specifications

**Goal:** Capture the CURRENT system behavior in documents so we don't accidentally break it.

```bash
# For each endpoint, document:
# 1. Request format (example JSON)
# 2. Response format (exact fields)
# 3. Error cases (what status codes, error messages)
# 4. Latency expectations
# 5. Dependency chain
```

**Deliverable:** `docs/API_SPECIFICATION.md`

```markdown
## GET /api/risk/comunas

### Request
```
GET /api/risk/comunas?include_history=true
```

### Response (200 OK)
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": 1,
        "name": "Arví",
        "risk_score": 0.65,
        "risk_category": "alto",
        "last_prediction": "2026-06-27T14:30:00Z"
      },
      "geometry": { ... GeoJSON polygon ... }
    }
  ]
}
```

### Performance Baseline
- Latency: P50=45ms, P95=120ms, P99=250ms (current FastAPI)
- Target with Go: P50=20ms, P95=60ms, P99=150ms

### Dependencies
- database: ml_features + risk_predictions + communes
- external: ArcGIS API for polygon fetch (cached)

### Error Cases
- 503 if ArcGIS API down → return cached geom from DB
- 400 if invalid parameters
```

**For each endpoint, also document:**
- SQL queries (EXPLAIN ANALYZE)
- Cache behavior (what should be cached?)
- Failure modes (what happens if dependency fails?)

### 0.2 Establish Feature Parity Matrix

**Goal:** Know EXACTLY what must work identically after refactor.

```
Feature                    | Current | Go API | HTMX Frontend | Status
---------------------------|---------|--------|---------------|---------
View latest risk map       | ✓ React | [ ]    | [ ]           | 
Select commune detail      | ✓ React | [ ]    | [ ]           | 
View 30-day rainfall       | ✓ Chart | [ ]    | [ ]           | 
Chat with bot              | ✓ Chat  | [ ]    | [ ]           | 
Get risk alerts            | ✓ API   | [ ]    | [ ]           | 
Scraper status dashboard   | ✓ API   | [ ]    | [ ]           | 
Manual trigger prediction  | ✓ API   | [ ]    | [ ]           | 
Session persistence        | ✓ DB    | [ ]    | [ ]           | 
Dark/light theme           | ✓ React | [ ]    | [ ]           | 
Responsive (mobile)        | ✓ React | [ ]    | [ ]           | 
```

**Critical rule:** If any feature is in "Current ✓" column, it MUST work in the refactored version.

### 0.3 Create "Parallel Run" Test Environment

**Goal:** Run Go API + HTMX frontend ALONGSIDE current FastAPI + React (same database).

```bash
# Keep current system on ports:
FastAPI:  localhost:8000
Next.js:  localhost:3000

# Run new system on ports:
Go API:   localhost:9000
HTMX:     localhost:9001

# Database: SHARED (same PostgreSQL)
```

This allows:
1. A/B testing (compare outputs)
2. Gradual migration (switch traffic slowly)
3. Rollback (just use old ports)

### 0.4 Set Up Monitoring & Alerting

**Before refactor, instrument the CURRENT system:**

```python
# Add metrics to FastAPI
from prometheus_client import Counter, Histogram

request_count = Counter('api_requests_total', 'Total requests', ['method', 'endpoint'])
request_duration = Histogram('api_request_duration_ms', 'Request duration', ['endpoint'])

@app.get("/api/risk/comunas")
async def get_risk_comunas():
    start = time.time()
    result = ...
    duration_ms = (time.time() - start) * 1000
    request_duration.labels(endpoint="get_risk_comunas").observe(duration_ms)
    return result
```

**Metrics to track (in Prometheus/Grafana):**
- Request latency (p50/p95/p99)
- Error rate by endpoint
- Database query time
- External API latency (ArcGIS, Ollama)
- Cache hit ratio

**Why:** During refactor, these metrics will tell you if Go API is actually faster.

---

## PHASE 1: ARCHITECTURE DESIGN & POC
**Duration:** 10-12 days (Week 1-2)

### 1.1 Define Service Contracts (Interface Specification)

**Goal:** Go API, Python microservices, and HTMX frontend must communicate via EXPLICIT contracts.

#### Contract 1: Go API ↔ Python Agent Service

```yaml
# Service: python-agent
# URL: http://python-agent:8001
# Calls: Per chat message

POST /api/v1/chat
Content-Type: application/json

{
  "session_id": "uuid-here",
  "territory_id": "medellin",
  "user_message": "¿Cuál es el riesgo en Altos del Cauca?",
  "context": {
    "current_risk_scores": { "1": 0.65, "2": 0.42, ... },
    "last_events": [ { ... } ]
  }
}

Response (200 OK):
{
  "assistant_message": "El riesgo en Altos del Cauca es ALTO (0.65)...",
  "session_id": "uuid-here",
  "timestamp": "2026-06-27T14:30:00Z",
  "confidence": 0.92,
  "sources": ["risk_predictions", "landslide_events"]
}
```

**Error contract:**
```json
{
  "error": "agent_service_unavailable",
  "message": "Python agent service not responding",
  "fallback": "Sorry, I'm temporarily offline. Try again in a moment.",
  "status": 503
}
```

#### Contract 2: Go API ↔ Python ML Service

```yaml
POST /api/v1/predict
Content-Type: application/json

{
  "territory_id": "medellin",
  "commune_id": "1",
  "features": {
    "precip_7d_mm": 45.3,
    "n_events_window": 2,
    "centroid_lat": 6.22,
    "centroid_lon": -75.56,
    ...
  }
}

Response (200 OK):
{
  "risk_score": 0.68,
  "risk_category": "alto",
  "model_version": "xgb-20260627-v1.2",
  "confidence_interval": [0.61, 0.75],
  "explanation": {
    "top_factors": [
      {"factor": "rainfall_7d", "contribution": 0.35},
      {"factor": "events_history", "contribution": 0.28}
    ]
  }
}
```

#### Contract 3: HTMX Frontend ↔ Go API

```yaml
GET /api/html/risk/map

Response (200 OK):
Content-Type: text/html

<div id="risk-map">
  <svg viewBox="0 0 100 100">
    <!-- Interactive SVG polygons or Canvas-based map -->
    <g class="commune" data-commune-id="1" onclick="htmx.ajax('GET', '/api/html/commune/1', '#detail')">
      <path d="..." fill="#ff6b6b" />
      <text>Altos del Cauca</text>
    </g>
  </svg>
</div>

<script>
// Polling for live updates (fallback)
setInterval(() => {
  htmx.ajax('GET', '/api/html/risk/status', '#status')
}, 30000);
</script>
```

### 1.2 Create Go API Skeleton

**Goal:** Prove Go can accept requests and delegate to Python services.

```bash
cd platform/backend
mkdir -p go-api
cd go-api

go mod init github.com/teyva/api
touch main.go
```

**Minimal main.go (100 LOC):**

```go
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
)

var (
	pythonAgentURL = os.Getenv("PYTHON_AGENT_URL") // "http://python-agent:8001"
	pythonMLURL    = os.Getenv("PYTHON_ML_URL")    // "http://python-ml:8002"
	postgresURL    = os.Getenv("DATABASE_URL")
)

func main() {
	http.HandleFunc("/health", healthCheck)
	http.HandleFunc("/api/health", healthCheck)

	// Risk endpoints
	http.HandleFunc("/api/risk/comunas", riskComunas)
	http.HandleFunc("/api/risk/predict", predictRisk)

	// Chat endpoints (delegate to Python)
	http.HandleFunc("/api/chat", chatHandler)

	// Health check should pass before serving
	if err := testConnections(); err != nil {
		log.Fatalf("Service dependencies unavailable: %v", err)
	}

	log.Println("Starting Go API on :8000")
	http.ListenAndServe(":8000", logMiddleware(http.DefaultServeMux))
}

func healthCheck(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"status":"ok","service":"go-api"}`)
}

func riskComunas(w http.ResponseWriter, r *http.Request) {
	// Read from PostgreSQL directly (using database/sql + pgx)
	// Return GeoJSON
	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"type":"FeatureCollection","features":[]}`)
}

func predictRisk(w http.ResponseWriter, r *http.Request) {
	// Forward to Python ML service via HTTP
	// pythonMLURL + "/api/v1/predict"
	fmt.Fprintf(w, `{}`)
}

func chatHandler(w http.ResponseWriter, r *http.Request) {
	// Forward to Python Agent service
	// pythonAgentURL + "/api/v1/chat"
	fmt.Fprintf(w, `{}`)
}

func testConnections() error {
	// Test PostgreSQL connection
	// Test Python service availability (retry 3x)
	// Test Ollama service availability
	return nil
}

func logMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		log.Printf("%s %s %s", r.Method, r.RequestURI, r.RemoteAddr)
		next.ServeHTTP(w, r)
	})
}
```

**Dockerfile for Go API:**

```dockerfile
# Build stage
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o api .

# Runtime stage
FROM alpine:3.18
RUN apk add --no-cache ca-certificates curl
COPY --from=builder /app/api /usr/local/bin/
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
ENTRYPOINT ["api"]
```

### 1.3 Extract Python Agent as HTTP Service

**Goal:** Chat logic runs as separate service, not inside API process.

**New structure:**

```
platform/backend/
├── go-api/                 # NEW Go API
├── python-services/        # NEW
│   ├── agent/
│   │   ├── main.py        # FastAPI service (200 LOC)
│   │   ├── chat.py        # Agent logic (MOVED from api/)
│   │   └── Dockerfile
│   ├── ml/
│   │   ├── main.py        # FastAPI service
│   │   ├── predict.py     # (unchanged)
│   │   └── Dockerfile
│   └── docker-compose.yml
└── scraper/               # unchanged
```

**agent/main.py (FastAPI microservice):**

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

app = FastAPI(title="TEYVA Agent Service")

class ChatRequest(BaseModel):
    session_id: str
    territory_id: str
    user_message: str
    context: dict = {}

class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    confidence: float
    sources: list

logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    # Initialize agent connections
    logger.info("Agent service starting")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent"}

@app.post("/api/v1/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        # Call existing agent.chat() function
        response = await agent_chat(
            request.user_message,
            request.session_id,
            request.context
        )
        return ChatResponse(
            session_id=request.session_id,
            assistant_message=response,
            confidence=0.92,
            sources=["risk_predictions"]
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=503, detail="Agent unavailable")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

### 1.4 Proof-of-Concept Testing

**Goal:** Validate that inter-service communication works.

**Test script (test_poc.sh):**

```bash
#!/bin/bash

echo "=== TEYVA Refactor PoC Test ==="

# 1. Start all services (docker-compose)
docker-compose -f platform/backend/docker-compose.yml up -d
sleep 10

# 2. Health checks
echo "Testing health endpoints..."
curl -f http://localhost:8000/health || exit 1
curl -f http://localhost:8001/health || exit 1

# 3. Test risk endpoint (Go API reads DB)
echo "Testing Go API /risk/comunas..."
RISK_RESPONSE=$(curl -s http://localhost:8000/api/risk/comunas)
if echo "$RISK_RESPONSE" | jq . > /dev/null 2>&1; then
  echo "✓ Risk endpoint works"
else
  echo "✗ Risk endpoint failed: $RISK_RESPONSE"
  exit 1
fi

# 4. Test chat endpoint (Go API → Python Agent)
echo "Testing Go API /chat..."
CHAT_RESPONSE=$(curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","user_message":"Hi"}')

if echo "$CHAT_RESPONSE" | jq '.assistant_message' > /dev/null 2>&1; then
  echo "✓ Chat endpoint works"
else
  echo "✗ Chat endpoint failed: $CHAT_RESPONSE"
  exit 1
fi

# 5. Compare with old system (if running on port 8000, Go; on 8001, FastAPI)
echo "Testing old FastAPI for comparison..."
# (optional)

echo ""
echo "=== PoC PASSED ==="
echo "Ready for full refactor"
```

### 1.5 Go/No-Go Decision Point

**End of Week 1, make decision:**

**GO if:**
- ✓ PoC passed all tests
- ✓ Go API < 150ms latency vs 45ms baseline (acceptable overhead)
- ✓ Team feels confident
- ✓ Stakeholders approve timeline

**NO-GO if:**
- ✗ PoC latency > 300ms (inter-service overhead too high)
- ✗ Team encounters blockers (Go experience gap)
- ✗ Business can't afford 8+ week downtime
- ✗ Database migration issues discovered

**If NO-GO:** Revert to current FastAPI + React, use Phase 0 insights to optimize existing system instead.

---

## PHASE 2: GO API DEVELOPMENT
**Duration:** 12-14 days (Week 3-4)

### 2.1 Go API Structure

```go
go-api/
├── main.go                 # Entry point
├── go.mod, go.sum
├── Dockerfile
├── handlers/
│   ├── risk.go            # /api/risk/* endpoints
│   ├── chat.go            # /api/chat/* endpoints
│   ├── scraper.go         # /api/scraper/* endpoints
│   └── health.go
├── middleware/
│   ├── auth.go            # JWT validation (if added)
│   ├── cors.go            # CORS handling
│   ├── logging.go         # Request logging
│   └── errors.go          # Error response formatting
├── models/
│   ├── risk.go            # RiskPrediction struct
│   ├── commune.go         # Commune struct
│   └── chat.go            # ChatMessage struct
├── db/
│   ├── postgres.go        # Connection pool
│   └── queries.go         # SQL queries (using sqlc)
├── services/
│   ├── risk.go            # Risk calculation logic
│   ├── python_agent.go    # HTTP client to agent service
│   ├── python_ml.go       # HTTP client to ML service
│   └── cache.go           # Redis/in-memory cache
└── config/
    └── config.go          # Environment variable loading
```

### 2.2 Key Implementation Details

#### Database Access (using sqlc for type-safe queries)

```bash
# Generate Go structs from SQL
cd platform/backend/go-api
sqlc generate

# This creates: db/models.go (auto-generated)
# with types like: type RiskPrediction struct { ... }
```

**sqlc.yaml:**

```yaml
version: "2"
sql:
  - engine: "postgresql"
    queries: "./queries/"
    schema: "./schema/"
    gen:
      go:
        package: "db"
        out: "db/models.go"
```

**queries/risk.sql:**

```sql
-- name: GetLatestRiskByCommune :one
SELECT 
  id, commune_id, risk_score, risk_category, model_version, created_at
FROM risk_predictions
WHERE commune_id = $1
ORDER BY created_at DESC
LIMIT 1;

-- name: GetAllCommuneRisks :many
SELECT 
  id, commune_id, risk_score, risk_category, created_at
FROM risk_predictions
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY commune_id, created_at DESC;
```

#### Error Handling

```go
// Define error types
type ErrorResponse struct {
	Code    string `json:"error"`
	Message string `json:"message"`
	Status  int    `json:"status"`
}

// Handle Python service failures gracefully
func getChatResponse(ctx context.Context, req ChatRequest) (string, error) {
	resp, err := httpClient.Post(pythonAgentURL + "/api/v1/chat", ...)
	
	if err != nil {
		// Service down
		return fallbackResponse(), nil // Return graceful fallback
	}
	
	if resp.StatusCode == 503 {
		// Temporary service issue
		return cachedResponse(req.SessionID), nil
	}
	
	// Parse response or return error
}
```

#### Caching Strategy

```go
// Cache ArcGIS polygon fetches (expensive, rarely change)
func getCommunePolygons(ctx context.Context) (GeoJSON, error) {
	// Try cache first (Redis or in-memory)
	if cached := cache.Get("commune_polygons"); cached != nil {
		return cached, nil
	}
	
	// Fetch from ArcGIS
	polygons := fetchFromArcGIS()
	
	// Cache for 24 hours
	cache.Set("commune_polygons", polygons, 24*time.Hour)
	
	return polygons, nil
}
```

### 2.3 Testing the Go API

**Unit tests (test_handlers.go):**

```go
import "testing"

func TestGetRiskComunas(t *testing.T) {
	// Setup test database
	db := setupTestDB(t)
	defer db.Close()
	
	// Seed test data
	insertTestPrediction(db, commune_id=1, risk_score=0.65)
	
	// Call handler
	req := httptest.NewRequest("GET", "/api/risk/comunas", nil)
	w := httptest.NewRecorder()
	
	handler := NewRiskHandler(db)
	handler.GetComunas(w, req)
	
	// Assert
	if w.Code != 200 {
		t.Fatalf("Expected 200, got %d", w.Code)
	}
	
	var response RiskResponse
	json.NewDecoder(w.Body).Decode(&response)
	
	if len(response.Features) == 0 {
		t.Fatal("Expected features in response")
	}
}
```

**Integration tests (docker-compose test environment):**

```bash
# Start test services
docker-compose -f docker-compose.test.yml up

# Run integration tests against real services
go test -tags=integration ./...

# Cleanup
docker-compose -f docker-compose.test.yml down
```

---

## PHASE 3: PYTHON MICROSERVICES EXTRACTION
**Duration:** 8-10 days (Week 4-5)

### 3.1 Agent Service (HTTP wrapper around existing agent)

**File:** `platform/backend/python-services/agent/main.py` (200 LOC)

```python
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

from ...agent.chat import agent_chat  # Import existing logic
from ...db.models import Conversation

app = FastAPI()

# Database
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Create tables if not exist
        pass

@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent"}

@app.post("/api/v1/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    async with async_session() as session:
        try:
            response = await agent_chat(
                message=request.user_message,
                session_id=request.session_id,
                db=session,
                context=request.context
            )
            
            return ChatResponse(
                session_id=request.session_id,
                assistant_message=response,
                confidence=0.92,
                sources=["risk_predictions", "landslide_events"]
            )
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(status_code=503)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

### 3.2 ML Service (HTTP wrapper around predictor)

**File:** `platform/backend/python-services/ml/main.py` (180 LOC)

```python
from fastapi import FastAPI, HTTPException
import joblib
import os
from pathlib import Path

from ...ml.predict import predict_commune_risk
from ...ml.features import FeatureBuilder
from ...db.models import RiskPrediction

app = FastAPI()

# Load model
MODEL_PATH = Path(os.getenv("ML_MODELS_DIR", "/models/best_model.pkl"))
scaler_path = MODEL_PATH.parent / "scaler.pkl"

model = joblib.load(str(MODEL_PATH))
scaler = joblib.load(str(scaler_path))

logger = logging.getLogger(__name__)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ml", "model_loaded": model is not None}

@app.post("/api/v1/predict")
async def predict(request: PredictRequest) -> PredictResponse:
    try:
        # Build features
        features = await FeatureBuilder.from_dict(request.features)
        
        # Predict
        risk_score = model.predict_proba(features)[0][1]
        risk_category = categorize_risk(risk_score)
        
        return PredictResponse(
            risk_score=risk_score,
            risk_category=risk_category,
            model_version="xgb-20260627-v1.2",
            explanation={"top_factors": [...]}
        )
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=503)
```

### 3.3 Scraper (stays mostly unchanged)

**No changes needed** - continues as daemon process.

```python
# platform/backend/intelligence/scraper/scheduler.py
# (already works independently)
```

---

## PHASE 4: FRONTEND REFACTOR (React → HTMX)
**Duration:** 18-22 days (Week 5-8) ← CRITICAL PATH

### 4.1 Component Port Strategy

**Easy components (4 days, 40% of work):**

```
✓ Header (navigation bar)
✓ KPI Cards (metric display)
✓ Commune Info Panel (text display)
✓ Alert Banner (notifications)
```

These are mostly HTML + CSS. No JavaScript beyond basic events.

**Hard components (8 days, 40% of work):**

```
✗ Medellin Map (Leaflet)
✗ Rainfall Chart (Chart.js)
```

These need special handling.

**Medium component (2 days, 10% of work):**

```
⚠ Chat Widget (stateful, localStorage)
```

### 4.2 Strategy for Hard Components

#### Option A: Keep as Embedded Iframes (Fastest)

Keep Leaflet map + Chart.js inside a Node.js micro-server, embed as iframe.

```html
<div id="map-container">
  <iframe src="http://localhost:9002/embedded-map" width="100%" height="600"></iframe>
</div>

<div id="chart-container">
  <iframe src="http://localhost:9002/embedded-chart?commune_id=1" width="100%" height="400"></iframe>
</div>
```

**Pros:**
- Fast (reuse existing React components)
- Low risk (no need to port complex logic)
- Works with HTMX frontend

**Cons:**
- Adds another service
- Slightly slower (iframe overhead ~50ms)

**Timeline:** 3 days (keep 30% of React, wrap in service)

#### Option B: Port to Vanilla JS + Canvas/SVG (Complete Refactor)

Build map + chart from scratch using:
- Canvas API for map rendering
- SVG for interactive commune polygons
- D3.js or PlotlyJS for chart

**Pros:**
- No embedded services
- Single Go API + HTML + JS

**Cons:**
- Geospatial calculations complex (10+ days)
- Chart library learning curve (3+ days)
- High risk of bugs

**Timeline:** 12-15 days

#### Option C: Use Lightweight Charting Library

Replace Chart.js with lightweight alternative that works in vanilla HTML.

- **Lightweight option 1:** PlotlyJS (50KB gzipped, works standalone)
- **Lightweight option 2:** ECharts (self-contained, no React needed)
- **Lightweight option 3:** Simple HTML table + CSS bar chart (manual)

**Recommendation:** Use **Option A (Embedded Iframe)** for MVP. Lowest risk, fastest time-to-market. Refactor to B later if needed.

### 4.3 HTMX + Vanilla HTML Structure

**New frontend structure:**

```
platform/frontend/
├── static/                # Served by Go API
│   ├── index.html        # Main page
│   ├── css/
│   │   └── style.css     # Tailwind compiled
│   └── js/
│       ├── app.js        # Main app logic
│       ├── map.js        # Map interactions (delegation)
│       └── chat.js       # Chat widget
├── templates/            # (if using template engine)
│   └── commune_detail.html
└── Dockerfile           # Nginx serving static files
```

**index.html (new structure with HTMX):**

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TEYVA - Risk Monitor</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body hx-boost="true" hx-ext="polling">
    <!-- Header -->
    <header id="header" hx-get="/api/html/header" hx-trigger="load">
        Loading...
    </header>

    <main class="container">
        <!-- Risk Map -->
        <section id="map-section">
            <h2>Risk Map (Last 24h)</h2>
            <div id="map-container" 
                 hx-get="/api/html/risk/map" 
                 hx-trigger="load, communeSelected from:body"
                 hx-swap="innerHTML">
                Loading map...
            </div>
        </section>

        <!-- KPI Cards -->
        <section id="kpi-section">
            <div hx-get="/api/html/kpi-cards" hx-trigger="load" hx-swap="innerHTML">
                Loading KPIs...
            </div>
        </section>

        <!-- Commune Details -->
        <section id="detail-section">
            <div id="commune-detail" 
                 hx-get="/api/html/commune/1" 
                 hx-trigger="load"
                 hx-swap="innerHTML">
                Select a commune
            </div>
        </section>

        <!-- Chat Widget -->
        <section id="chat-section">
            <div hx-get="/api/html/chat" hx-trigger="load" hx-swap="innerHTML">
                Loading chat...
            </div>
        </section>
    </main>

    <script src="/js/app.js"></script>
</body>
</html>
```

**app.js (HTMX event handling):**

```javascript
document.body.addEventListener('htmx:afterSettle', function(evt) {
    // Re-attach event listeners after HTMX swap
    initializeEventListeners();
});

function selectCommune(communeId) {
    // Trigger HTMX to fetch new detail
    htmx.ajax('GET', `/api/html/commune/${communeId}`, '#commune-detail');
    
    // Update map highlight
    htmx.ajax('GET', `/api/html/risk/map?highlight=${communeId}`, '#map-container');
}

function initializeEventListeners() {
    document.querySelectorAll('[data-commune-id]').forEach(el => {
        el.addEventListener('click', e => {
            selectCommune(e.target.dataset.communeId);
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeEventListeners);
```

### 4.4 Go API Endpoints for HTML

**New endpoints in Go API (serve HTML fragments):**

```go
// handlers/html.go

func (h *Handler) GetRiskMapHTML(w http.ResponseWriter, r *http.Request) {
	// Query database for latest risk + commune polygons
	communities, err := h.db.GetAllCommuneRisks(r.Context())
	if err != nil {
		http.Error(w, "Database error", 500)
		return
	}
	
	// Render HTML with embedded SVG or canvas
	html := renderMapHTML(communities)
	w.Header().Set("Content-Type", "text/html")
	fmt.Fprint(w, html)
}

func renderMapHTML(communities []Community) string {
	// Generate SVG for each commune
	svg := `<svg viewBox="0 0 100 100">`
	for _, c := range communities {
		color := riskColorClass(c.RiskScore)
		svg += fmt.Sprintf(`
			<g class="commune %s" data-commune-id="%d" onclick="selectCommune(%d)">
				<polygon points="%s" />
				<text>%s</text>
			</g>
		`, color, c.ID, c.ID, c.PolygonSVG, c.Name)
	}
	svg += `</svg>`
	return svg
}
```

---

## PHASE 5: CONTAINERIZATION & ORCHESTRATION
**Duration:** 10-12 days (Week 8-9)

### 5.1 Multi-Container Architecture

**docker-compose.yml (production-like):**

```yaml
version: '3.9'

services:
  # Database (same as before)
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: teyva
      POSTGRES_USER: teyva
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U teyva"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Go API (new)
  go-api:
    build:
      context: .
      dockerfile: platform/backend/go-api/Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgres://teyva:${DB_PASSWORD}@postgres:5432/teyva
      PYTHON_AGENT_URL: http://python-agent:8001
      PYTHON_ML_URL: http://python-ml:8002
      PYTHON_SCRAPER_URL: http://python-scraper:8003
      OLLAMA_URL: http://ollama:11434
      LOG_LEVEL: info
    depends_on:
      postgres:
        condition: service_healthy
      python-agent:
        condition: service_healthy
      python-ml:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Python Agent Service (new)
  python-agent:
    build:
      context: .
      dockerfile: platform/backend/python-services/agent/Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://teyva:${DB_PASSWORD}@postgres:5432/teyva
      OLLAMA_URL: http://ollama:11434
      LOG_LEVEL: info
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Python ML Service (new)
  python-ml:
    build:
      context: .
      dockerfile: platform/backend/python-services/ml/Dockerfile
    environment:
      DATABASE_URL: postgresql://teyva:${DB_PASSWORD}@postgres:5432/teyva
      ML_MODELS_DIR: /models
      LOG_LEVEL: info
    volumes:
      - ml_models:/models
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Python Scraper Daemon (kept as-is)
  python-scraper:
    build:
      context: .
      dockerfile: platform/backend/intelligence/scraper/Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://teyva:${DB_PASSWORD}@postgres:5432/teyva
      LOG_LEVEL: info
    volumes:
      - scraper_logs:/var/log/scraper
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  # LLM Service (unchanged)
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  # HTMX Frontend
  frontend:
    build:
      context: .
      dockerfile: platform/frontend/Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_BASE: http://go-api:8000
    depends_on:
      - go-api
    restart: unless-stopped

volumes:
  postgres_data:
  ollama_data:
  ml_models:
  scraper_logs:

networks:
  default:
    name: teyva-network
```

### 5.2 Dockerfile for Each Service

**Go API (platform/backend/go-api/Dockerfile):**

```dockerfile
# Build stage
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY platform/backend/go-api/go.mod go.sum ./
RUN go mod download
COPY platform/backend/go-api . ./
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o api .

# Runtime stage
FROM alpine:3.18
RUN apk add --no-cache ca-certificates curl
WORKDIR /app
COPY --from=builder /app/api ./api
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
CMD ["./api"]
```

**Python Agent Service (platform/backend/python-services/agent/Dockerfile):**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY platform/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY platform/backend/python-services/agent . ./
COPY platform/backend/intelligence . ./intelligence
COPY platform/backend/db . ./db

EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s CMD curl -f http://localhost:8001/health || exit 1
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 5.3 Environment Configuration

**.env (development):**

```env
# Database
DB_PASSWORD=dev_password_only
DATABASE_URL=postgresql+asyncpg://teyva:${DB_PASSWORD}@postgres:5432/teyva

# Services
PYTHON_AGENT_URL=http://python-agent:8001
PYTHON_ML_URL=http://python-ml:8002
PYTHON_SCRAPER_URL=http://python-scraper:8003

# LLM
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2

# API
NEXT_PUBLIC_API_BASE=http://localhost:8000
LOG_LEVEL=debug
```

**.env.prod (production):**

```env
# Database (use managed service)
DATABASE_URL=postgresql+asyncpg://teyva:${VAULT_DB_PASSWORD}@rds.amazonaws.com:5432/teyva

# Services (internal Kubernetes endpoints)
PYTHON_AGENT_URL=http://python-agent:8001
PYTHON_ML_URL=http://python-ml:8002

# LLM
OLLAMA_URL=http://ollama-cluster:11434

# API
NEXT_PUBLIC_API_BASE=https://api.teyva.co
LOG_LEVEL=info
```

---

## PHASE 6: INTEGRATION TESTING
**Duration:** 8-10 days (Week 9-10)

### 6.1 Test Strategy

**Unit Tests (per-service):**
- Go API: `go test ./...` (test each handler + middleware)
- Python Agent: `pytest -v` (test chat logic)
- Python ML: `pytest -v` (test prediction accuracy)

**Integration Tests (cross-service):**

```bash
# Start docker-compose test environment
docker-compose -f docker-compose.test.yml up

# Run integration tests
pytest tests/integration/test_full_flow.py -v
go test -tags=integration ./... -v

# E2E tests (real browser)
npx playwright test
```

### 6.2 Critical Test Cases

```python
# tests/integration/test_full_flow.py

def test_end_to_end_risk_flow():
    """
    1. User requests risk map
    2. Go API queries database
    3. Returns GeoJSON
    4. Frontend renders map
    5. User clicks commune
    6. HTMX fetches detail
    7. Detail shows chat
    8. User sends message
    9. Go API calls Python agent
    10. Agent calls Ollama
    11. Response shown to user
    """
    # Implement

def test_python_agent_unavailable():
    """If Python agent crashes, Go API should gracefully degrade"""
    # Stop python-agent service
    # Call /api/chat
    # Should return 503 with fallback message

def test_database_connection_pool():
    """All 6 services with 10 connections each shouldn't exceed 100 total"""
    # Stress test with concurrent requests
    # Assert: no "too many connections" error

def test_cross_service_latency():
    """P95 latency should not increase > 200% from baseline"""
    # Baseline (single-process FastAPI): 45ms
    # After refactor: < 135ms
    # Measure: Go API → Python Agent → Ollama → Go API

def test_data_consistency():
    """Same request to old API (port 8000) and new API (port 9000) should return same data"""
    # Send identical request to both
    # Compare JSON responses
    # Assert: identical (with timestamps ignored)
```

### 6.3 Performance Benchmarking

```bash
# Use Apache Bench or wrk to load test
ab -n 1000 -c 10 http://localhost:8000/api/risk/comunas
wrk -t4 -c100 -d30s http://localhost:8000/api/risk/comunas

# Capture metrics
# Compare: baseline (FastAPI) vs new (Go API)
# - Throughput (req/sec)
# - Latency (p50, p95, p99)
# - Error rate
# - CPU usage
# - Memory usage
```

---

## PHASE 7: DEPLOYMENT & HARDENING
**Duration:** 8-10 days (Week 10-11)

### 7.1 Pre-Production Checklist

- [ ] All tests passing (unit, integration, E2E)
- [ ] Performance benchmarks meet targets (or documented variance)
- [ ] Database migration tested (old → new schema)
- [ ] Data validation complete (same results, both systems)
- [ ] Security review completed (Go API handlers)
- [ ] Monitoring configured (Prometheus metrics exported)
- [ ] Alerting configured (PagerDuty, Slack)
- [ ] Incident response runbook written
- [ ] Rollback procedure tested

### 7.2 Gradual Rollout Strategy

```
Day 1: Canary (5% traffic)
├─ 95% → old FastAPI
├─ 5% → new Go API + HTMX
└─ Monitor metrics closely

Day 2-3: Ramp (25% traffic)
├─ 75% → old FastAPI
├─ 25% → new Go API + HTMX

Day 4-5: Full (100% traffic)
├─ 0% → old FastAPI
├─ 100% → new Go API + HTMX

Day 6-7: Monitor only (no rollback)
├─ If issues, can still rollback to Day 1 state
├─ After 48h, disable old FastAPI services
```

### 7.3 Monitoring Setup

**Prometheus metrics to export from Go API:**

```go
// Instrument Go API
var (
	httpRequestDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name: "http_request_duration_seconds",
			Buckets: []float64{.005, .01, .025, .05, .1, .25, .5, 1},
		},
		[]string{"method", "endpoint", "status"},
	)
	httpRequestsTotal = prometheus.NewCounterVec(...)
)

// Collect metrics
func metricsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		duration := time.Since(start).Seconds()
		httpRequestDuration.WithLabelValues(
			r.Method,
			r.URL.Path,
			strconv.Itoa(w.StatusCode),
		).Observe(duration)
	})
}
```

**Grafana dashboard:**
- Request latency (p50, p95, p99)
- Error rate per endpoint
- Service availability (Python agent, ML, database)
- Resource usage (CPU, memory, connections)

---

## ROLLBACK PROCEDURES

### If Something Goes Wrong (Decision Tree)

```
Is the system down? (Y/N)
├─ Y: IMMEDIATE ROLLBACK (switch traffic back to old FastAPI on port 8000)
└─ N: Continue diagnosis

Error rate > 5%? (Y/N)
├─ Y: Check which service is failing
│  ├─ Python Agent? Rollback to old chat endpoint
│  ├─ Go API? Rollback entire system
│  └─ Database? Check connectivity, restart postgres
└─ N: Monitor, don't rollback yet

Latency > 500ms? (Y/N)
├─ Y: Check service logs for slow queries
│  ├─ Database slow? Optimize queries, check indexes
│  ├─ External API slow? Add caching, check network
│  └─ Service call slow? Increase timeout, check Python service logs
└─ N: Performance is acceptable

Data inconsistency? (Y/N)
├─ Y: IMMEDIATE ROLLBACK
│  ├─ Restore database from backup
│  └─ Investigate bug before re-deploying
└─ N: Proceed with caution
```

### Rollback Command

```bash
# If using docker-compose
docker-compose stop go-api python-agent python-ml

# Restart old FastAPI (if not containerized)
docker-compose down
docker-compose -f docker-compose.old.yml up

# If using Kubernetes
kubectl rollout undo deployment/go-api
kubectl rollout undo deployment/python-agent
kubectl rollout undo deployment/python-ml

# Verify rollback
curl http://localhost:8000/health
# Should respond with FastAPI version info
```

---

## SUCCESS METRICS

**Refactor is successful if:**

1. **Functionality Parity**
   - ✓ All endpoints respond with same data (old vs new)
   - ✓ Chat works without degradation
   - ✓ Map renders correctly
   - ✓ All 4 scrapers still running

2. **Performance** (within 10% of baseline)
   - ✓ Risk endpoint: < 100ms (was 45ms)
   - ✓ Chat endpoint: < 300ms (was 100ms)
   - ✓ Frontend load: < 2s (was 1.5s)
   - ✓ Throughput: > 1000 req/sec (was 1200 req/sec)

3. **Reliability**
   - ✓ Uptime > 99.5% (no unplanned downtime)
   - ✓ Error rate < 0.1%
   - ✓ Database connections stable (no leaks)

4. **Code Quality**
   - ✓ Test coverage > 70%
   - ✓ No security vulnerabilities (OWASP top 10)
   - ✓ Logs are useful for debugging
   - ✓ Services can restart without data loss

5. **Operations**
   - ✓ Can deploy new version in < 5 min
   - ✓ Can rollback in < 2 min
   - ✓ Alerts fire for real issues (not false positives)
   - ✓ On-call engineer can debug issues independently

**If any metric fails: ROLLBACK immediately, fix root cause, then re-attempt.**

---

## TIMELINE SUMMARY

| Phase | Duration | Key Deliverable | Risk Level |
|-------|----------|-----------------|-----------|
| Phase 0 | 3-5 days | API spec + monitoring setup | 🟢 Low |
| Phase 1 | 10-12 days | Go API PoC (test endpoints working) | 🟡 Medium |
| Phase 2 | 12-14 days | Go API production-ready | 🟡 Medium |
| Phase 3 | 8-10 days | Python microservices extracted | 🟡 Medium |
| Phase 4 | 18-22 days | HTMX frontend complete | 🔴 HIGH |
| Phase 5 | 10-12 days | Docker setup, service orchestration | 🟡 Medium |
| Phase 6 | 8-10 days | Integration testing complete | 🟡 Medium |
| Phase 7 | 8-10 days | Gradual rollout, full production | 🟡 Medium |
| **TOTAL** | **8-11 weeks** | **Complete refactor live** | **🔴 HIGH** |

---

## TEAM COMPOSITION

**Required skills:**

| Role | Seniority | FTE | Responsibility |
|------|-----------|-----|---|
| Go Developer | Senior | 2.0 | Go API, service communication, performance |
| Python Developer | Senior | 1.0 | Microservices extraction, ML wrapping |
| Frontend Developer | Senior | 1.0 | React → HTMX, map/chart portability |
| DevOps Engineer | Mid | 1.0 | Docker, Compose, monitoring, CI/CD |
| QA Engineer | Mid | 0.5 | Integration testing, load testing |

---

## CRITICAL DECISION POINTS

### End of Phase 1 (Week 2)

**Question:** Does the PoC latency meet acceptable thresholds?

- **If YES:** Continue to Phase 2
- **If NO:** Investigate root cause (Go overhead, network, DB)
  - If unfixable: Consider keeping FastAPI, just port frontend
  - If fixable: Adjust architecture, extend Phase 1

### End of Phase 4 (Week 8)

**Question:** Can HTMX handle the map + chart complexity?

- **If YES:** Continue to Phase 5
- **If NO:** Revert to iframe strategy (keeps React components)
  - This extends timeline but reduces technical risk

### End of Phase 6 (Week 10)

**Question:** Is performance acceptable and all data consistent?

- **If YES:** Proceed to Phase 7 (gradual rollout)
- **If NO:** HOLD and debug before going to production
  - Don't rush to Phase 7 with known issues

---

## WORST-CASE SCENARIO

**If refactor fails halfway through:**

1. **Abort immediately** (don't try to "push through")
2. **Restore old system** from Week 0 backup
3. **Analyze what went wrong:**
   - Was it architecture? (Go + Python microservices too complex)
   - Was it team capacity? (Underestimated effort)
   - Was it unknown unknowns? (Unforeseen dependencies)
4. **Plan next iteration:**
   - Smaller scope (e.g., just Go API, keep FastAPI for now)
   - More time for research + prototyping
   - Different approach (keep more of current system)

---

## RECOMMENDATION

**Given the complexity, consider:**

1. **Start with Phase 0-1 only** (2-3 weeks)
   - Build the spec document + PoC
   - Make go/no-go decision with full information
   - If uncertain, pivot to lower-risk alternatives

2. **Alternative: Phased Approach**
   - Month 1: Port API to Go ONLY (keep Python for ML, agent, scraper)
   - Month 2: Optimize Python microservices (remove FastAPI overhead)
   - Month 3: Frontend refactor to HTMX + embedded services

This reduces weekly risk from "everything breaks" to "one component at a time."

---

**Plan created:** June 2026  
**Owner:** Architecture Team  
**Status:** Ready for kickoff decision
