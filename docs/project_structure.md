# Estructura del Proyecto — TEYVA

Mapa completo del repositorio con la descripción de cada carpeta y archivo relevante.

---

```
teyva/
├── RECURSOS/                          # Material visual de la presentación
├── docs/                              # Documentación técnica y metodológica
├── data/                              # Ciclo de vida de los datos
├── notebooks/                         # Análisis exploratorio y experimentación
├── src/                               # Módulos de alto nivel (interfaz pública)
├── platform/                          # Código fuente de producción
├── models/                            # Artefactos de modelos entrenados
├── reports/                           # Resultados y figuras exportadas
├── tests/                             # Pruebas unitarias, integración y equidad
├── config/                            # Configuración del entorno y modelos
├── deployments/                       # Infraestructura: Docker, Kubernetes, serverless
└── .github/                           # CI/CD y gestión del repositorio
```

---

## RECURSOS/

Material visual de la competencia. No contiene código.

| Archivo | Descripción |
|---|---|
| `Monitoreo-inteligente-de-riesgo-de-deslizamientos-para-Medellin.pptx` | Presentación original en PowerPoint |
| `Monitoreo-inteligente-de-riesgo-de-deslizamientos-para-Medellin.pdf` | Presentación exportada a PDF |
| `Portada.png` | Imagen de la diapositiva principal |

---

## docs/

Toda la documentación técnica, metodológica y de impacto del proyecto.

| Archivo | Descripción |
|---|---|
| `planteamiento_problema.md` | Contexto territorial, brechas identificadas, objetivo general y pregunta de investigación |
| `marco_metodologico.md` | Metodología CRISP-ML aplicada: fases, decisiones de modelado, métricas y gobernanza del pipeline |
| `fuentes_datos.md` | Fuentes de datos abiertos: URLs, licencias, frecuencia de ingesta y variables consumidas |
| `data_dictionary.md` | Definición de las 15+ variables del consolidado (tipos, rangos, fuente, descripción) |
| `api_spec.md` | Documentación de todos los endpoints REST en formato OpenAPI |
| `public_impact_assessment.md` | Evaluación de impacto público, análisis ético, sesgos identificados y mitigaciones |
| `conclusiones.md` | Hallazgos principales, limitaciones y hoja de ruta de próximos pasos |
| `validacion_guide.md` | Guía paso a paso para que pares o jueces validen los resultados de forma independiente |
| `project_structure.md` | Este documento — mapa completo del repositorio |
| `architecture/README.md` | Diagramas de arquitectura: sistema completo, flujo de datos y pipeline ML |
| `AGENTS.md` | Contratos entre agentes internos (ML, Chat, Scraper, API) |
| `DESIGN_SYSTEM.md` | Sistema de diseño del dashboard: paleta, tipografía, componentes |
| `REFACTOR_PLAN.md` | Plan de evolución técnica a Go API + microservicios Python (8–11 semanas) |

---

## data/

Gestión del ciclo de vida de los datos. Ver `data/README.md` para detalle.

| Carpeta | Descripción |
|---|---|
| `raw/` | Datos originales sin procesar descargados de SIATA, DAGRD, IDEAM, GeoMedellín y datos.gov.co. **Excluido de git** (voluminoso). |
| `processed/` | Datos limpios tras el pipeline de limpieza y transformación, listos para el modelo |
| `realtime/` | Buffers temporales de flujos en tiempo real (snapshots de APIs cada 30 min–6 h) |
| `external/` | Datos auxiliares: polígonos GeoJSON, shapefiles de quebradas, tablas de referencia de suelos |

---

## notebooks/

Experimentación, análisis exploratorio y generación de reportes. Ejecutar en orden.

| Notebook | Descripción |
|---|---|
| `01_EDA_exploracion_datos.ipynb` | Exploración inicial: estructura, calidad, valores nulos, distribuciones temporales por fuente |
| `02_limpieza_transformacion.ipynb` | Pipeline de limpieza: imputación, outliers (winsorizing), encoding, ventanas temporales (1d/3d/7d) |
| `03_analisis_descriptivo.ipynb` | Estadísticas básicas, mapa de correlaciones, distribución de variables, desbalance de clases |
| `04_modelo_predictivo.ipynb` | Entrenamiento XGBoost + SMOTE, validación temporal, curva ROC, matriz de confusión, importancia de variables |
| `05_reportes_automaticos.ipynb` | Generación automatizada de reportes ejecutivos, gráficos dinámicos y exportación a PDF |

---

## src/

Módulos de alto nivel que exponen la funcionalidad del sistema como interfaz pública reutilizable. Delegan internamente en `platform/backend/`.

```
src/
├── __init__.py
├── inference.py              # RiskPredictor: predicción on-demand y batch
├── train.py                  # ModelTrainer: reentrenamiento y freeze de benchmark
├── agents/
│   ├── citizen_agent.py      # CitizenAgent: interfaz conversacional para ciudadanos
│   └── analyst_agent.py      # AnalystAgent: generador de reportes para equipos técnicos
├── data_pipeline/
│   ├── ingest.py             # DataIngester: dispara scrapers de todas las fuentes
│   └── transform.py          # FeatureTransformer: construye features y vectoriza para RAG
└── features/
    └── __init__.py           # Ingeniería de características (referencia a platform/backend/ml/)
```

---

## platform/

Código fuente de producción. Es el núcleo del sistema.

```
platform/
├── backend/                  # Paquete Python único (PYTHONPATH apunta aquí)
│   ├── domain/               # Reglas de negocio puras (sin I/O): umbrales, categorías, territorio
│   ├── application/          # Casos de uso: predict_risk, fire_alerts, train_model
│   ├── infrastructure/       # Repositorios y clientes externos (ArcGIS, Slack, OSRM, LLM)
│   ├── ml/                   # Motor ML: train.py, predict.py, benchmark.py, modelos/
│   ├── scraper/              # Scrapers SIATA, DAGRD, IDEAM, GeoMedellín, sismos + scheduler
│   ├── db/                   # SQLAlchemy async/sync, session.py, 12+ modelos
│   ├── api/                  # FastAPI: routes/, auth.py, rate_limit.py, audit.py
│   ├── agent/                # Agente conversacional: Claude + Ollama, RAG, 8 tools, MCP
│   ├── rag/                  # ChromaDB + sentence-transformers (2,127 chunks)
│   ├── alerts/               # Slack, Snake Line, evacuación, reportes
│   └── alembic/              # Migraciones de esquema (10+)
└── frontend/                 # Next.js 16 + React 19 + Tailwind 4
    ├── components/dashboard/ # Mapa, KPIs, chat, historial, monitor de lluvia
    └── lib/api.ts            # Cliente fetch centralizado
```

---

## models/

Artefactos de modelos entrenados. Ver `models/README.md` para detalle.

| Carpeta | Descripción |
|---|---|
| `predictive/` | Modelo XGBoost: `best_model.pkl`, `scaler.pkl`, `feature_names.json`, `metrics.json`, `benchmark.json` |
| `llm_rag/` | Recursos del sistema conversacional: prompt de sistema, esquemas de tools, config ChromaDB |
| `simulation/` | Modelos de simulación de escenarios (en desarrollo): precipitación extrema, cambio climático |

> Los artefactos reales de producción viven en `platform/backend/ml/models/`. Esta carpeta es el espejo documentado para revisión técnica.

---

## reports/

Resultados visibles y exportables. Ver `reports/README.md` para cómo regenerarlos.

```
reports/
├── figures/
│   ├── distribuciones.png     # Generado por notebook 03
│   ├── correlaciones.png      # Generado por notebook 03
│   └── matriz_confusion.png   # Generado por notebook 04
└── reporte_final.pdf          # Exportado desde notebook 05
```

---

## tests/

Cobertura de pruebas en tres niveles.

| Carpeta | Descripción |
|---|---|
| `unit/` | Pruebas unitarias de reglas de negocio (`test_risk_rules.py`) e inferencia (`test_inference.py`) — sin dependencias externas |
| `integration/` | Pruebas contra la API en vivo (`test_api_endpoints.py`) — requieren backend corriendo en localhost:8000 |
| `bias_tests/` | Pruebas automatizadas de equidad y sesgo algorítmico (`test_algorithmic_fairness.py`) — recall mínimo, variables prohibidas, contaminación circular |

Ejecutar: `pytest tests/ -v --tb=short`

---

## config/

Configuración centralizada del entorno y los modelos. No contiene secretos.

| Archivo | Descripción |
|---|---|
| `base_config.yaml` | Parámetros generales: servidor, BD, ML, RAG, alertas, scrapers, CORS |
| `model_hyperparams.yaml` | Hiperparámetros de XGBoost, Random Forest, Logistic Regression, SMOTE, LLMs y embeddings |
| `security_policy.json` | Políticas de autenticación, rate limiting, anonimización, gobernanza y sesgo |

> Las variables sensibles (tokens, contraseñas, URLs de BD) van en `.env` — nunca en esta carpeta.

---

## deployments/

Infraestructura para despliegue en distintos entornos.

```
deployments/
├── docker/
│   ├── Dockerfile.api          # Imagen para la API REST + agente conversacional
│   └── Dockerfile.inference    # Imagen optimizada para el pipeline ML (CPU)
├── kubernetes/
│   ├── deployment.yaml         # Deployment + Service para la API en K8s
│   └── hpa.yaml                # Autoescalado horizontal (2–10 réplicas por CPU/memoria)
└── serverless/
    └── README.md               # Configuración Lambda para reportes automatizados
```

> Para desarrollo local usar `docker compose up` desde la raíz — levanta el stack completo en un comando.

---

## .github/

Automatización CI/CD y gestión del repositorio.

| Archivo | Descripción |
|---|---|
| `workflows/ci-cd-pipeline.yml` | Lint (ruff), type-check (mypy), pruebas unitarias + bias, build de imágenes Docker y frontend |
| `workflows/data-update-cron.yml` | Verificación de salud de fuentes cada 2 horas + detección de fuentes obsoletas |
| `workflows/scraper-siata.yml` | Ingesta SIATA cada 30 min |
| `workflows/scraper-dagrd.yml` | Ingesta DAGRD cada 1 h |
| `workflows/scraper-ideam.yml` | Ingesta IDEAM cada 6 h |
| `workflows/scraper-medellin.yml` | Ingesta GeoMedellín cada 24 h |
| `workflows/scraper-siata-sismos.yml` | Ingesta de sismos cada 30 min |
| `workflows/predict-risk.yml` | Predicción batch de riesgo para las 21 comunas |
| `workflows/ci-security.yml` | Análisis de seguridad y detección de secretos |
| `workflows/ci-tests.yml` | Suite de pruebas en CI |
| `workflows/monitor-api-health.yml` | Monitor de salud de la API |
| `CODEOWNERS` | Asignación de responsables por módulo para revisión de PRs |

---

## Archivos raíz

| Archivo | Descripción |
|---|---|
| `README.md` | Ficha técnica completa, instalación, arquitectura y acceso rápido |
| `LICENSE` | Licencia MIT |
| `Changelog.md` | Registro cronológico de versiones y cambios |
| `requirements.txt` | Dependencias Python fijadas para reproducibilidad |
| `environment.yml` | Entorno Conda con Python 3.11 y todas las dependencias |
| `.env.example` | Plantilla de variables de entorno (sin valores reales) |
| `.gitignore` | Exclusión de datos voluminosos, credenciales, artefactos de runtime y cachés |
| `docker-compose.yml` | Stack completo local: BD, Ollama, backend, frontend, scraper, ML |
| `CLAUDE.md` | Contexto técnico del proyecto para el agente de desarrollo |
