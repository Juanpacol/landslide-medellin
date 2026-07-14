# Marco Metodológico — CRISP-ML

TEYVA aplica la metodología **CRISP-ML(Q)** (Cross-Industry Standard Process for Machine Learning with Quality Assurance), adaptada al contexto de riesgo territorial y datos abiertos institucionales.

---

## Fase 1 — Comprensión del negocio y los datos

**Objetivo de negocio:** Reducir el tiempo de respuesta ante deslizamientos en Medellín mediante predicción anticipada a 7 días.

**Criterio de éxito del modelo:**
- AUC-ROC ≥ 0.90 (discriminación general)
- Recall ≥ 0.95 (prioridad: no omitir eventos reales)
- Precisión aceptable (se tolera cierto nivel de falsas alarmas para garantizar seguridad)

**Restricciones identificadas:**
- Desbalance extremo de clases: 26 eventos positivos reales / 8,429 muestras totales.
- Datos sintéticos (Snake Line) disponibles para calibración pero excluidos del entrenamiento para evitar contaminación circular.
- Latencia de datos: SIATA actualiza cada 30 min, IDEAM cada 6 h — el pipeline debe tolerar datos faltantes.

---

## Fase 2 — Comprensión y adquisición de datos

| Fuente | Tipo | Frecuencia | Variables clave |
|--------|------|-----------|----------------|
| SIATA | API REST + scraping | 30 min | precipitación mm, humedad suelo, temperatura |
| DAGRD | Scraping web | 1 h | tipo emergencia, barrio, fecha |
| IDEAM | API REST | 6 h | pronóstico regional, viento, presión |
| GeoMedellín / ArcGIS | API REST | 24 h | polígonos, pendiente, uso suelo |

**Exploración inicial (EDA):** Ver [`notebooks/01_EDA_exploracion_datos.ipynb`](../notebooks/01_EDA_exploracion_datos.ipynb)

---

## Fase 3 — Preparación de datos

### 3.1 Limpieza
- Deduplicación por `source_row_id` en cada scraper.
- Imputación de valores faltantes: mediana por ventana temporal de 7 días por comuna.
- Detección de outliers: IQR sobre precipitación acumulada.

### 3.2 Transformación
- Ventanas temporales: acumulados de 1d, 3d, 7d para precipitación.
- Encoding de variables categóricas (tipo de suelo, uso del suelo).
- Normalización con `StandardScaler` (persiste en `scaler.pkl` para inferencia).

### 3.3 Ingeniería de características
- `precip_7d_mm`: precipitación acumulada 7 días.
- `n_events_window`: eventos DAGRD en ventana de 30 días.
- `pendiente_promedio`: pendiente media del terreno por comuna.
- `dias_lluvia_consecutivos`: racha de días con precipitación > umbral.
- Ver diccionario completo en [`docs/data_dictionary.md`](data_dictionary.md).

**Notebook:** [`notebooks/02_limpieza_transformacion.ipynb`](../notebooks/02_limpieza_transformacion.ipynb)

---

## Fase 4 — Modelado

### 4.1 Selección de candidatos
Se evaluaron tres algoritmos con validación cruzada estratificada (5 folds):

| Modelo | AUC-ROC (CV) | Recall | Observación |
|--------|-------------|--------|-------------|
| XGBoost | **0.944** | **0.999** | Seleccionado |
| Random Forest | 0.921 | 0.987 | Segunda opción |
| Logistic Regression | 0.874 | 0.941 | Baseline |

### 4.2 Manejo del desbalance
Se aplicó **SMOTE** (Synthetic Minority Over-sampling Technique) sobre el conjunto de entrenamiento para generar instancias sintéticas de la clase minoritaria (deslizamientos). El conjunto de validación se mantuvo con la distribución real para no inflar métricas.

### 4.3 Validación temporal
Además de la validación cruzada, se realizó **validación temporal pasado→futuro** (`train_auc_temporal`): los modelos se entrenaron con datos hasta una fecha de corte y se validaron con datos posteriores, simulando el uso real.

### 4.4 Umbrales de clasificación
Definidos en `domain/risk_rules.py`:
- **Bajo:** score < 0.35
- **Medio:** 0.35 ≤ score < 0.65
- **Alto:** 0.65 ≤ score < 0.90
- **Crítico:** score ≥ 0.90

**Notebook:** [`notebooks/04_modelo_predictivo.ipynb`](../notebooks/04_modelo_predictivo.ipynb)

---

## Fase 5 — Evaluación

**Métricas finales del modelo en producción:**

| Métrica | Valor |
|---------|-------|
| AUC-ROC | 0.944 |
| Recall (sensibilidad) | 0.999 |
| Precisión | 0.87 |
| F1-Score | 0.93 |
| `train_auc_temporal` | Ver `ml/models/metrics.json` |
| `benchmark_auc` | Ver `ml/models/benchmark.json` |

**Matriz de confusión:** [`reports/figures/matriz_confusion.png`](../reports/figures/matriz_confusion.png)

---

## Fase 6 — Despliegue

- **Inferencia batch:** `python -m ml.predict` — corre vía GitHub Actions como cron job, escribe resultados en `risk_predictions`.
- **Inferencia on-demand:** `POST /api/risk/predict-commune` — requiere autenticación con rol admin.
- **Reentrenamiento:** `python -m ml.train` — ejecutable manualmente o vía workflow `predict-risk.yml`. Los 4 artefactos (`best_model.pkl`, `scaler.pkl`, `feature_names.json`, `metrics.json`) se escriben juntos o no se escriben, para evitar estados inconsistentes.
- **Monitoreo:** `metrics.json` incluye `trained_at` y `git_commit_sha` para trazabilidad.

---

## Gobernanza del pipeline

- Las migraciones de BD (Alembic) **nunca se editan** — cualquier cambio de esquema es una migración nueva.
- Los eventos sintéticos (`is_synthetic=true`) están **excluidos del entrenamiento** — solo se usan para calibrar Snake Line.
- El benchmark fijo (`benchmark.json`) se congela manualmente y sirve como línea base para detectar regresión del modelo.
