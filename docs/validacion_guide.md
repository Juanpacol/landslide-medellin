# Guía de Validación de Resultados

Esta guía permite que un evaluador externo o par técnico reproduzca y valide los resultados de TEYVA de forma independiente.

---

## 1. Requisitos previos

- Docker Desktop instalado y corriendo, **o** Python 3.11+ con las dependencias de `requirements.txt`.
- Acceso al repositorio (clonar o descargar ZIP).
- Opcional: credenciales de Supabase para validar con datos en vivo. Sin ellas, se puede usar la BD local del Docker Compose.

---

## 2. Levantar el entorno

```bash
git clone <repo-url>
cd teyva

# Opción A — Docker (recomendado, un solo comando)
docker compose up

# Opción B — Local
conda env create -f environment.yml
conda activate teyva
cd platform/backend
cp ../../.env.example .env
# Editar .env con DATABASE_URL local y dejar ANTHROPIC_API_KEY vacío para usar Ollama
export PYTHONPATH=.
alembic upgrade head
uvicorn api.main:app --reload --port 8000
```

Verificar que la API responde: `curl http://localhost:8000/api/health`  
Respuesta esperada: `{"status":"ok"}`

---

## 3. Validar el modelo ML

### 3.1 Ejecutar el entrenamiento
```bash
cd platform/backend
python -m ml.train
```

Verificar que se generaron los artefactos:
```
platform/backend/ml/models/
├── best_model.pkl        ← modelo serializado
├── scaler.pkl            ← escalador
├── feature_names.json    ← nombres de variables
└── metrics.json          ← AUC-ROC, Recall, F1, trained_at, git_commit_sha
```

Abrir `metrics.json` y verificar:
- `auc_roc` ≥ 0.93
- `recall` ≥ 0.99

### 3.2 Ejecutar el notebook de validación
```bash
jupyter notebook notebooks/04_modelo_predictivo.ipynb
```

El notebook genera:
- Curva ROC con AUC
- Matriz de confusión (también en `reports/figures/matriz_confusion.png`)
- Validación temporal pasado→futuro

### 3.3 Comparar con el benchmark fijo
```bash
python -m ml.benchmark
```
El benchmark lee `ml/models/benchmark.json` y compara con las métricas actuales. Si el AUC cae más de 0.05 puntos respecto al benchmark, se considera regresión del modelo.

---

## 4. Validar las predicciones en vivo

### 4.1 Predicción batch
```bash
python -m ml.predict
```

Verificar en la BD que se insertaron predicciones en `risk_predictions`:
```bash
# Con psql o pgAdmin
SELECT commune_id, risk_score, risk_category, created_at
FROM risk_predictions
ORDER BY created_at DESC
LIMIT 21;
```

Deben aparecer 21 filas (una por comuna) con `created_at` reciente.

### 4.2 Predicción via API
```bash
curl http://localhost:8000/api/risk/comunas
```

La respuesta debe ser un GeoJSON con 21 features, cada una con `risk_score` (0–1) y `risk_category` (bajo/medio/alto/critico).

---

## 5. Validar el agente conversacional

### 5.1 Via API
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Cuál es el riesgo en San Javier hoy?", "session_id": "test-validacion"}'
```

La respuesta debe:
- Mencionar el nivel de riesgo actual de San Javier (comuna 13).
- Estar redactada en lenguaje natural, sin scores numéricos.
- Incluir recomendación si el riesgo es alto o crítico.

### 5.2 Via dashboard
Abrir `http://localhost:3000`, hacer clic en cualquier comuna del mapa y usar el chat embebido.

### 5.3 Validar las 8 herramientas del agente
Preguntas de prueba para cada herramienta:

| Herramienta | Pregunta de prueba |
|---|---|
| `get_risk_predictions` | "¿Qué comunas tienen mayor riesgo ahora?" |
| `get_recent_events` | "¿Cuántos deslizamientos hubo esta semana?" |
| `get_rainfall_timeseries` | "¿Cuánto ha llovido en Manrique los últimos 7 días?" |
| `search_knowledge` | "¿Qué es la zona geotécnica Villatina?" |
| `get_scraper_health` | "¿Cómo están las fuentes de datos?" |
| `get_situation_report` | "Dame un resumen de la situación hoy" |
| `get_evacuation_routes` | "¿Adónde evacuo si estoy en San Javier?" |
| `report_incident` | "Quiero reportar grietas en una pared en la Floresta" |

---

## 6. Validar los scrapers

```bash
# Ver estado de todos los scrapers
curl http://localhost:8000/api/scraper/status
```

Campos a verificar:
- `status`: debe ser `ok` para todas las fuentes activas.
- `last_run`: debe ser reciente (< 2 horas para SIATA, < 7 horas para IDEAM).
- `records_valid`: puede ser 0 si no hay registros nuevos — esto es normal, no es error.

---

## 7. Checklist de validación completa

```
[ ] API responde en /api/health con status "ok"
[ ] ml.train genera metrics.json con AUC-ROC ≥ 0.93
[ ] ml.predict inserta 21 predicciones en risk_predictions
[ ] GET /api/risk/comunas retorna GeoJSON con 21 features
[ ] Chat responde con datos reales de la BD (menciona nivel de riesgo actual)
[ ] Las 8 herramientas del agente responden correctamente
[ ] Los scrapers tienen status "ok" o "sin registros nuevos"
[ ] La matriz de confusión en reports/figures/ coincide con metrics.json
```

---

## 8. Contacto para dudas técnicas

**Juan Pablo Botero** — jbotero@aztia.co  
Issues en el repositorio: abrir un ticket con la etiqueta `validacion`.
