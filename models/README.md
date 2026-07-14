# Modelos — TEYVA

## Estructura

```
models/
├── predictive/   # Artefactos del modelo XGBoost de predicción de riesgo
├── llm_rag/      # Embeddings, prompts y configuración del sistema conversacional
└── simulation/   # Modelos de simulación de escenarios
```

## predictive/
Artefactos del modelo ML en producción (generados por `python -m ml.train`):

| Archivo | Descripción |
|---|---|
| `best_model.pkl` | Modelo XGBoost serializado con joblib |
| `scaler.pkl` | StandardScaler ajustado al conjunto de entrenamiento |
| `feature_names.json` | Lista ordenada de variables que espera el modelo |
| `metrics.json` | AUC-ROC, Recall, F1, trained_at, git_commit_sha |
| `benchmark.json` | Snapshot fijo de métricas de referencia (congelar con `python -m ml.benchmark --freeze`) |

> Los artefactos reales viven en `platform/backend/ml/models/`. Esta carpeta es el espejo documentado para revisión técnica.

## llm_rag/
Configuración y recursos del sistema conversacional:

| Archivo | Descripción |
|---|---|
| `system_prompt.txt` | Prompt de sistema del agente TEYVA |
| `tool_schemas.json` | Esquemas JSON de las 8 herramientas del agente |
| `embed_model.txt` | Modelo de embeddings: `paraphrase-multilingual-MiniLM-L12-v2` |
| `chroma_config.json` | Configuración de la colección ChromaDB |

> Los vectores reales de ChromaDB viven en `platform/backend/rag/`. Regenerar con `python -m rag.chroma_store --ingest`.

## simulation/
Modelos de simulación de escenarios de riesgo bajo condiciones hipotéticas:

- Simulación de precipitación extrema (eventos 1-en-10-años, 1-en-50-años)
- Análisis de sensibilidad de umbrales de alerta
- Escenarios de cambio climático (temperatura +1.5°C, +2°C)

> En desarrollo. Ver `docs/conclusiones.md` — Próximos pasos.
