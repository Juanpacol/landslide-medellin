# TEYVA — Monitoreo Inteligente de Riesgo de Deslizamientos para Medellín

> Plataforma de datos abiertos + IA para anticipar, comunicar y gestionar el riesgo de deslizamientos en las 21 comunas de Medellín.

---

## Ficha Técnica

| Campo | Detalle |
|---|---|
| **Nombre del proyecto** | TEYVA |
| **Problema abordado** | Dispersión de datos de riesgo de deslizamientos sin integración ni predicción anticipada para las comunas de ladera de Medellín |
| **Justificación** | Los deslizamientos son la segunda causa de emergencias en Medellín. Las comunidades en ladera no cuentan con alertas tempranas accesibles ni información unificada en tiempo real. TEYVA centraliza 4 fuentes institucionales de datos abiertos, predice el riesgo 7 días antes y lo comunica en lenguaje natural a operarios y ciudadanos |
| **Cantidad de datasets utilizados** | 4 fuentes primarias + 1 dataset de datos.gov.co |
| **Dataset principal** | SIATA — Red hidrometeorológica de Medellín (precipitación, sensores de suelo) |
| **Datasets externos** | DAGRD (emergencias), IDEAM (meteorología nacional), GeoMedellín/ArcGIS (cartografía) |
| **Variables seleccionadas** | 15+ variables: precipitación acumulada 7d, eventos históricos, pendiente de ladera, humedad del suelo, temperatura, uso del suelo, cobertura vegetal, sismos recientes. Ver [`docs/data_dictionary.md`](docs/data_dictionary.md) |
| **Tipo de análisis** | Predictivo (clasificación binaria de riesgo por comuna) |
| **Modelo utilizado** | XGBoost con SMOTE (balanceo de clases) |
| **Resultados clave** | AUC-ROC: **0.944** · Recall: **0.999** · 26 eventos reales / 8,429 muestras |
| **Interpretación** | El modelo identifica correctamente el 99.9% de los eventos reales de deslizamiento. El umbral conservador evita falsos negativos en un contexto de riesgo a la vida |
| **Impacto potencial** | Reducción del tiempo de respuesta de Gestión del Riesgo · Alertas 7 días antes del evento · Acceso ciudadano a información de riesgo en lenguaje natural · Rutas de evacuación calculadas automáticamente |

---

## Solución en Producción (Demo en Vivo)

- **Aplicación Web:** [`http://localhost:3000`](http://localhost:3000) — Dashboard con mapa de 21 comunas, KPIs en tiempo real, chat con IA y monitor de lluvia
- **API REST:** [`http://localhost:8000/docs`](http://localhost:8000/docs) — Documentación interactiva Swagger/OpenAPI
- **Contenedor listo:** `docker compose up` levanta el stack completo en un comando

---

## Acceso Rápido

| Recurso | Enlace |
|---|---|
| Presentación (PPTX) | [`RECURSOS/Monitoreo-inteligente-de-riesgo-de-deslizamientos-para-Medellin.pptx`](RECURSOS/Monitoreo-inteligente-de-riesgo-de-deslizamientos-para-Medellin.pptx) |
| Presentación (PDF) | [`RECURSOS/Monitoreo-inteligente-de-riesgo-de-deslizamientos-para-Medellin.pdf`](RECURSOS/Monitoreo-inteligente-de-riesgo-de-deslizamientos-para-Medellin.pdf) |
| Portada | [`RECURSOS/Portada.png`](RECURSOS/Portada.png) |
| Informe técnico | [`docs/marco_metodologico.md`](docs/marco_metodologico.md) |
| Diccionario de datos | [`docs/data_dictionary.md`](docs/data_dictionary.md) |
| Arquitectura del sistema | [`docs/architecture/`](docs/architecture/) |
| Evaluación de impacto | [`docs/public_impact_assessment.md`](docs/public_impact_assessment.md) |
| Especificación API | [`docs/api_spec.md`](docs/api_spec.md) |
| Guía de validación | [`docs/validacion_guide.md`](docs/validacion_guide.md) |

---

## Arquitectura General

```
Fuentes externas (SIATA · DAGRD · IDEAM · GeoMedellín)
        ↓  [scrapers cada 30min–24h]
PostgreSQL / Supabase  ←→  ChromaDB (2,127 chunks RAG)
        ↓
  XGBoost ML (AUC 0.944)          Agente conversacional
  Predicción a 7 días         (Claude + Ollama fallback)
        ↓                              ↓ 8 herramientas
   FastAPI REST API  ←─────────────────┘
        ↓
   Dashboard Next.js 16 + React 19
   (mapa · KPIs · chat · alertas Slack)
```

Capas de la solución:
- `domain/` — reglas puras de negocio (sin I/O)
- `application/` — casos de uso (predicción, alertas, entrenamiento)
- `infrastructure/` — repositorios, clientes externos (ArcGIS, Slack, OSRM)
- `api/` — FastAPI REST con autenticación por roles y rate limiting
- `agent/` — agente conversacional con tool-calling y RAG

---

## Stack Tecnológico

**Backend:** Python 3.11 · FastAPI · SQLAlchemy async · Alembic · APScheduler  
**ML:** XGBoost · Scikit-learn · SMOTE (imbalanced-learn) · joblib  
**IA conversacional:** Anthropic Claude Haiku 4-5 · Ollama (llama3.2) · ChromaDB · sentence-transformers  
**Base de datos:** PostgreSQL · Supabase (Connection Pooler)  
**Frontend:** Next.js 16 · React 19 · Tailwind 4 · Leaflet · Radix/shadcn  
**Infraestructura:** Docker · GitHub Actions (9 workflows) · OSRM · ArcGIS API · Slack API  

---

## Instalación Rápida

### Opción A — Docker (recomendado)

```bash
git clone <repo>
cd teyva
docker compose up
```

Abre [http://localhost:3000](http://localhost:3000). Primera ejecución descarga el modelo LLM (~2 GB).

### Opción B — Local

```bash
# Crear entorno
conda env create -f environment.yml
conda activate teyva

# Backend
cd platform/backend
export PYTHONPATH=.
cp ../../.env.example .env   # completar credenciales
alembic upgrade head
uvicorn api.main:app --reload --port 8000

# Frontend (otra terminal)
cd platform/frontend
pnpm install && pnpm dev
```

### Variables de entorno requeridas

Ver [`.env.example`](.env.example) — las mínimas son `DATABASE_URL`, `ANTHROPIC_API_KEY` (o usar Ollama local) y `SLACK_WEBHOOK_URL` (opcional).

---

## Entrenamiento y Predicción

```bash
cd platform/backend
python -m ml.train      # entrena modelo, guarda artefactos en ml/models/
python -m ml.predict    # genera predicciones batch para todas las comunas
python -m ml.benchmark --freeze   # congela benchmark de referencia
```

---

## Estructura del Repositorio

```
teyva/
│
├── RECURSOS/                        # 📊 Presentación (PPTX, PDF, portada)
│
├── docs/                            # 📚 Documentación técnica y metodológica
│   ├── project_structure.md         #    ↳ Este mapa, con detalle de cada carpeta
│   ├── planteamiento_problema.md
│   ├── marco_metodologico.md        #    ↳ CRISP-ML, fases, decisiones
│   ├── fuentes_datos.md             #    ↳ SIATA · DAGRD · IDEAM · GeoMedellín
│   ├── data_dictionary.md           #    ↳ 15+ variables definidas
│   ├── api_spec.md                  #    ↳ Endpoints REST (OpenAPI)
│   ├── public_impact_assessment.md  #    ↳ Impacto, ética, sesgos
│   ├── conclusiones.md
│   ├── validacion_guide.md
│   └── architecture/                #    ↳ Diagramas de arquitectura
│
├── data/                            # 🗄  Ciclo de vida de los datos
│   ├── raw/                         #    ↳ Datos originales (excluido de git)
│   ├── processed/                   #    ↳ Datos limpios y transformados
│   ├── realtime/                    #    ↳ Buffers de flujos en tiempo real
│   └── external/                    #    ↳ Datos auxiliares (polígonos, shapefiles)
│
├── notebooks/                       # 📓 Análisis y experimentación (ejecutar en orden)
│   ├── 01_EDA_exploracion_datos.ipynb
│   ├── 02_limpieza_transformacion.ipynb
│   ├── 03_analisis_descriptivo.ipynb
│   ├── 04_modelo_predictivo.ipynb   #    ↳ XGBoost + SMOTE, curva ROC, matriz confusión
│   └── 05_reportes_automaticos.ipynb
│
├── src/                             # 🧩 Interfaz pública de alto nivel
│   ├── inference.py                 #    ↳ RiskPredictor (predicción on-demand y batch)
│   ├── train.py                     #    ↳ ModelTrainer (reentrenamiento)
│   ├── agents/
│   │   ├── citizen_agent.py         #    ↳ Chat conversacional para ciudadanos
│   │   └── analyst_agent.py         #    ↳ Reportes automáticos para equipos técnicos
│   └── data_pipeline/
│       ├── ingest.py                #    ↳ Dispara scrapers de las 4 fuentes
│       └── transform.py             #    ↳ Construye features y vectoriza para RAG
│
├── platform/                        # ⚙️  Código fuente de producción
│   ├── backend/                     #    ↳ Python: ML · API · agente · scrapers · BD
│   └── frontend/                    #    ↳ Next.js 16 + React 19 + Tailwind 4
│
├── models/                          # 🤖 Artefactos de modelos entrenados
│   ├── predictive/                  #    ↳ best_model.pkl · scaler · metrics · benchmark
│   ├── llm_rag/                     #    ↳ Prompts, schemas de tools, config ChromaDB
│   └── simulation/                  #    ↳ Escenarios hipotéticos (en desarrollo)
│
├── reports/                         # 📈 Resultados exportados
│   └── figures/                     #    ↳ distribuciones · correlaciones · matriz_confusion
│
├── tests/                           # 🧪 Pruebas en tres niveles
│   ├── unit/                        #    ↳ Reglas de negocio e inferencia (sin dependencias)
│   ├── integration/                 #    ↳ Endpoints API en vivo (requiere backend)
│   └── bias_tests/                  #    ↳ Equidad algorítmica y variables prohibidas
│
├── config/                          # ⚙️  Configuración centralizada (sin secretos)
│   ├── base_config.yaml             #    ↳ Servidor, BD, ML, RAG, alertas, scrapers
│   ├── model_hyperparams.yaml       #    ↳ XGBoost, SMOTE, LLMs, embeddings
│   └── security_policy.json         #    ↳ Auth, rate limiting, anonimización, sesgos
│
├── deployments/                     # 🚀 Infraestructura de despliegue
│   ├── docker/                      #    ↳ Dockerfile.api · Dockerfile.inference
│   ├── kubernetes/                  #    ↳ deployment.yaml · hpa.yaml
│   └── serverless/                  #    ↳ Funciones Lambda para reportes automáticos
│
├── .github/                         # 🔄 CI/CD y automatización
│   ├── workflows/                   #    ↳ 11 workflows: scrapers · predict · lint · build
│   └── CODEOWNERS                   #    ↳ Responsables por módulo
│
├── README.md                        # ← estás aquí
├── LICENSE                          # MIT
├── Changelog.md                     # Historial de versiones
├── requirements.txt                 # Dependencias Python fijadas
├── environment.yml                  # Entorno Conda
├── .env.example                     # Plantilla de variables de entorno
└── docker-compose.yml               # Stack completo local (un comando)
```

> Detalle completo de cada carpeta y archivo en [`docs/project_structure.md`](docs/project_structure.md).

---

## Documentación Adicional

| Documento | Descripción |
|---|---|
| [`docs/project_structure.md`](docs/project_structure.md) | Mapa completo del repositorio — qué hay en cada carpeta y para qué sirve |
| [`docs/planteamiento_problema.md`](docs/planteamiento_problema.md) | Definición del problema, contexto territorial y necesidad pública |
| [`docs/marco_metodologico.md`](docs/marco_metodologico.md) | Metodología CRISP-ML aplicada, fases y decisiones |
| [`docs/fuentes_datos.md`](docs/fuentes_datos.md) | Fuentes de datos abiertos, URLs, licencias y frecuencia |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | Definición de las 15+ variables del consolidado |
| [`docs/api_spec.md`](docs/api_spec.md) | Endpoints REST documentados en formato OpenAPI |
| [`docs/public_impact_assessment.md`](docs/public_impact_assessment.md) | Evaluación de impacto, ética y mitigación de sesgos |
| [`docs/conclusiones.md`](docs/conclusiones.md) | Hallazgos principales, limitaciones y próximos pasos |
| [`docs/validacion_guide.md`](docs/validacion_guide.md) | Guía para que pares validen los resultados |
| [`docs/architecture/`](docs/architecture/) | Diagramas de arquitectura del sistema |

---

## Equipo

**Owner / Desarrollador principal:** Juan Pablo Botero — jbotero@aztia.co  
**Stakeholder institucional:** Gestión del Riesgo de Medellín (DAGRD)  
**Última actualización:** Julio 2026
