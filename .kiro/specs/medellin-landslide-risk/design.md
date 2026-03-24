# Design Document: Sistema de Análisis de Riesgo de Deslizamientos — Medellín

## Overview

Sistema web de una sola página para análisis y visualización de riesgo de deslizamientos en Medellín, orientado a demo de hackathon. Integra tres fuentes de datos públicas (emergencias históricas, precipitación diaria, cartografía comunas) para producir un mapa coroplético de riesgo, gráficas de correlación y alertas por umbral de precipitación.

El diseño prioriza velocidad de desarrollo: un solo repositorio, sin Docker, sin microservicios, ejecutable con dos comandos (`python pipeline.py` + `python app.py`).

Stack:
- Backend: Python 3.11 + FastAPI
- Base de datos: Supabase (PostgreSQL hosted) via `supabase-py`
- Pipeline: script único `pipeline.py` con pandas + geopandas + scipy
- Frontend: HTML + Vanilla JS + Leaflet.js + Chart.js (sin frameworks)

---

## Architecture

```
medellin-landslide-risk/
├── pipeline.py          # Descarga, procesa y guarda en Supabase
├── app.py               # Servidor FastAPI, sirve API + archivos estáticos
├── .env                 # SUPABASE_URL y SUPABASE_KEY (no commitear)
├── data/
│   ├── raw/             # CSVs crudos descargados (conservados 30 días)
│   └── comunas.geojson  # GeoJSON de comunas (descargado por pipeline)
├── static/
│   ├── index.html
│   ├── app.js
│   └── style.css
└── requirements.txt
```

Flujo de datos:

```
Fuentes externas
  ├── medata.gov.co (emergencias CSV)
  ├── datos.gov.co / SIATA (precipitación CSV)
  └── GeoMedellín (comunas GeoJSON)
        │
        ▼
   pipeline.py
   (descarga → filtra → normaliza → calcula correlaciones → calcula índice → guarda)
        │
        ▼
   Supabase (PostgreSQL hosted)
   tablas: events, precipitation, communes, alerts, data_quality_log
        │
        ▼
   app.py (FastAPI)
   GET /api/risk-index
   GET /api/events
   GET /api/alerts
   GET /api/status
   GET /api/export/csv
   GET /api/export/geojson
        │
        ▼
   index.html + app.js
   (Leaflet mapa + Chart.js gráficas + alertas banner)
```

Conexión a Supabase:

```python
# Patrón de conexión en pipeline.py y app.py
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
```

---

## Components and Interfaces

### pipeline.py

Módulo único con funciones secuenciales. Sin clases complejas.

```python
# Funciones principales
def ingest_emergencies() -> pd.DataFrame
def ingest_precipitation() -> pd.DataFrame
def ingest_geodata() -> dict          # GeoJSON como dict
def compute_correlations(events, precip) -> pd.DataFrame
def compute_risk_index(events, precip, geo) -> pd.DataFrame
def evaluate_alerts(precip) -> list[dict]
def save_to_supabase(client, ...)     # Guarda todos los resultados via supabase-py
def run_pipeline()                    # Orquesta todo
```

### app.py (FastAPI)

```python
GET  /                          # Sirve index.html
GET  /api/risk-index            # Índice de riesgo por comuna (JSON)
GET  /api/events                # Eventos filtrados por commune_id, fecha_inicio, fecha_fin
GET  /api/alerts                # Alertas activas
GET  /api/status                # Estado de calidad de datos
GET  /api/export/csv            # Descarga CSV de índice de riesgo
GET  /api/export/geojson        # Descarga GeoJSON enriquecido
```

Cada endpoint consulta Supabase directamente via `supabase-py`:

```python
# Ejemplo de consulta en app.py
result = supabase.table("communes").select("*").execute()
```

### Frontend (index.html + app.js)

Tres paneles:
1. Mapa Leaflet coroplético (comunas coloreadas por riesgo) + marcadores de eventos
2. Panel lateral: detalle de comuna al hacer clic
3. Gráficas Chart.js: serie de tiempo doble eje + scatter precipitación vs eventos
4. Banner de alertas en la parte superior
5. Panel de estado de datos (última actualización, % válidos)

---

## Data Models

### Supabase — tablas SQL

Las tablas se crean una vez en el dashboard de Supabase (SQL Editor) antes de ejecutar el pipeline.

```sql
-- Eventos de deslizamiento filtrados
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    source_row_id   TEXT,
    fecha           TEXT,       -- ISO 8601
    tipo_emergencia TEXT,
    commune_id      TEXT,
    barrio          TEXT,
    latitud         REAL,
    longitud        REAL,
    has_coords      BOOLEAN
);

-- Precipitación diaria con acumulados
CREATE TABLE precipitation (
    id                    BIGSERIAL PRIMARY KEY,
    fecha                 TEXT,
    estacion              TEXT,
    precipitacion_mm      REAL,
    precipitacion_acum_3d REAL,
    precipitacion_acum_7d REAL,
    cod_municipio         TEXT
);

-- Comunas con topografía e índice de riesgo
CREATE TABLE communes (
    commune_id          TEXT PRIMARY KEY,
    nombre_comuna       TEXT,
    pendiente_promedio  REAL,
    is_zona_ladera      BOOLEAN,
    indice_riesgo       REAL,
    categoria_riesgo    TEXT,       -- Bajo/Medio/Alto/Crítico
    indice_parcial      BOOLEAN,
    n_eventos           INTEGER,
    correlacion_diaria  REAL,
    correlacion_3d      REAL,
    correlacion_7d      REAL,
    geometry            TEXT        -- GeoJSON geometry como string JSON
);

-- Alertas generadas
CREATE TABLE alerts (
    id                  BIGSERIAL PRIMARY KEY,
    commune_id          TEXT,
    nivel               TEXT,       -- Naranja / Rojo
    precipitacion_valor REAL,
    tipo_umbral         TEXT,       -- diaria / acum_3d
    timestamp           TEXT
);

-- Log de calidad de datos
CREATE TABLE data_quality_log (
    id                    BIGSERIAL PRIMARY KEY,
    fuente                TEXT,
    fecha_ingesta         TEXT,
    registros_descargados INTEGER,
    registros_validos     INTEGER,
    registros_descartados INTEGER,
    motivo_descarte       TEXT,
    estado                TEXT        -- OK / Error
);
```

### Operaciones Supabase en pipeline.py

```python
# Upsert de comunas (reemplaza en cada ejecución del pipeline)
supabase.table("communes").upsert(communes_records).execute()

# Insert de eventos (append)
supabase.table("events").insert(events_records).execute()

# Insert de alertas
supabase.table("alerts").insert(alert_records).execute()

# Insert de log de calidad
supabase.table("data_quality_log").insert(log_record).execute()
```

### Modelos de respuesta API (Pydantic)

```python
class CommuneRisk(BaseModel):
    commune_id: str
    nombre_comuna: str
    indice_riesgo: float | None
    categoria_riesgo: str | None
    n_eventos: int
    correlacion_3d: float | None
    precipitacion_acum_7d: float | None
    pendiente_promedio: float | None
    is_zona_ladera: bool

class SlideEvent(BaseModel):
    id: int
    fecha: str
    tipo_emergencia: str
    commune_id: str
    latitud: float | None
    longitud: float | None

class Alert(BaseModel):
    commune_id: str
    nivel: str
    precipitacion_valor: float
    tipo_umbral: str
    timestamp: str

class DataStatus(BaseModel):
    fuente: str
    fecha_ultima_actualizacion: str | None
    porcentaje_validos: float | None
    estado: str
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Filtrado de eventos por tipo de emergencia

*For any* DataFrame de emergencias, todos los registros en el resultado del filtro deben contener 'desliz' o 'movimiento' en el campo `tipo_emergencia` (sin distinción de mayúsculas), y ningún registro que no cumpla esa condición debe aparecer en el resultado.

**Validates: Requirements 1.2**

---

### Property 2: Normalización de fechas a ISO 8601

*For any* registro de emergencia o precipitación con un campo `fecha` en cualquier formato de entrada válido, el valor normalizado debe coincidir con el patrón `YYYY-MM-DD`.

**Validates: Requirements 1.6, 2.4**

---

### Property 3: Marcado de registros sin coordenadas

*For any* registro de emergencia donde `latitud` o `longitud` sea nulo o vacío, el campo `has_coords` en el resultado debe ser `False`.

**Validates: Requirements 1.4**

---

### Property 4: Validación de precipitación negativa o no numérica

*For any* DataFrame de precipitación, ningún registro con `precipitacion_mm` negativo o no numérico debe aparecer en el resultado procesado.

**Validates: Requirements 2.5**

---

### Property 5: Cálculo de acumulados de precipitación

*For any* serie de precipitación diaria ordenada por fecha, el valor de `precipitacion_acum_3d` en el día D debe ser igual a la suma de `precipitacion_mm` de los días D-2, D-1 y D; y `precipitacion_acum_7d` debe ser la suma de los 7 días hasta D inclusive.

**Validates: Requirements 2.6**

---

### Property 6: Validación de esquema GeoJSON y filtrado de features inválidos

*For any* GeoJSON de comunas, el resultado procesado debe contener únicamente features que tengan `commune_id`, `nombre_comuna` y `geometry` de tipo Polygon o MultiPolygon; cualquier feature que no cumpla esas condiciones debe ser excluido.

**Validates: Requirements 3.2, 3.3**

---

### Property 7: Clasificación de Zona_Ladera

*For any* comuna con `pendiente_promedio` mayor o igual a 15 grados, el campo `is_zona_ladera` debe ser `True`; para cualquier comuna con `pendiente_promedio` menor a 15 grados, debe ser `False`.

**Validates: Requirements 3.6**

---

### Property 8: Correlaciones de Spearman en rango válido y manejo de datos insuficientes

*For any* conjunto de datos de comunas, si una comuna tiene 10 o más eventos, sus correlaciones (`correlacion_diaria`, `correlacion_3d`, `correlacion_7d`) deben estar en el rango [-1.0, 1.0]; si tiene menos de 10 eventos, las tres correlaciones deben ser `None`.

**Validates: Requirements 4.1, 4.2, 4.3, 4.5**

---

### Property 9: Cálculo y normalización del Índice de Riesgo

*For any* conjunto de comunas con datos completos, el `indice_riesgo` calculado debe estar en el rango [0.0, 1.0], y la `categoria_riesgo` debe corresponder al intervalo correcto: Bajo [0.0–0.25), Medio [0.25–0.50), Alto [0.50–0.75), Crítico [0.75–1.0].

**Validates: Requirements 5.1, 5.2, 5.3**

---

### Property 10: Índice parcial cuando falta pendiente

*For any* comuna sin dato de `pendiente_promedio`, el campo `indice_parcial` debe ser `True` y el `indice_riesgo` debe calcularse usando únicamente frecuencia (peso 0.5) y precipitación (peso 0.5).

**Validates: Requirements 5.4**

---

### Property 11: Generación de alertas por umbral de precipitación

*For any* estación meteorológica asociada a una Zona_Ladera, si `precipitacion_mm` diaria supera 50 mm debe generarse una alerta de nivel Naranja; si `precipitacion_acum_3d` supera 100 mm debe generarse una alerta de nivel Rojo.

**Validates: Requirements 8.2, 8.3**

---

### Property 12: Ordenamiento de alertas por severidad

*For any* lista de alertas activas, las alertas de nivel Rojo deben aparecer antes que las de nivel Naranja en el resultado ordenado.

**Validates: Requirements 8.5**

---

### Property 13: Persistencia de alertas (round-trip)

*For any* alerta generada por el Alertador, consultando la tabla `alerts` en Supabase debe retornar un registro con los mismos valores de `commune_id`, `nivel`, `precipitacion_valor`, `tipo_umbral` y `timestamp`.

**Validates: Requirements 8.6**

---

### Property 14: Esquema de exportación CSV

*For any* exportación CSV generada por `/api/export/csv`, el archivo debe contener exactamente las columnas: `commune_id`, `nombre_comuna`, `indice_riesgo`, `categoria_riesgo`, `n_eventos`, `correlacion_3d`, `precipitacion_acum_7d` y `pendiente_promedio`.

**Validates: Requirements 9.1**

---

### Property 15: Filtrado de eventos por parámetros de API

*For any* llamada a `GET /api/events` con parámetros `commune_id`, `fecha_inicio` y/o `fecha_fin`, todos los eventos retornados deben cumplir los criterios de filtro especificados.

**Validates: Requirements 9.5**

---

### Property 16: Trazabilidad de eventos mediante source_row_id

*For any* evento procesado y almacenado en Supabase, el campo `source_row_id` debe estar presente y no ser nulo.

**Validates: Requirements 10.5**

---

### Property 17: Esquema del log de calidad de datos

*For any* ejecución del pipeline, el registro insertado en `data_quality_log` debe contener los campos: `fuente`, `fecha_ingesta`, `registros_descargados`, `registros_validos`, `registros_descartados`, `motivo_descarte` y `estado`.

**Validates: Requirements 10.1**

---

## Error Handling

Estrategia minimalista para demo de hackathon:

- **Descarga fallida**: Si `requests.get()` lanza excepción, el pipeline registra el error en `data_quality_log` con `estado = "Error"` y continúa con los datos ya existentes en Supabase. FastAPI sigue sirviendo los datos previos.
- **Supabase no disponible**: Si `supabase-py` lanza excepción en cualquier operación, el pipeline imprime el error y termina con código de salida 1. `app.py` retorna HTTP 503 con mensaje descriptivo.
- **Variables de entorno faltantes**: Si `SUPABASE_URL` o `SUPABASE_KEY` no están definidas, tanto `pipeline.py` como `app.py` fallan inmediatamente con mensaje claro: `"Error: SUPABASE_URL y SUPABASE_KEY deben estar definidas en .env"`.
- **Datos insuficientes**: Comunas con < 10 eventos reciben correlaciones `null` y el índice se calcula con los componentes disponibles. No se lanza excepción.
- **GeoJSON inválido**: Features sin `commune_id` o `geometry` válida son omitidos con advertencia en log. El pipeline continúa con los features válidos.

---

## Testing Strategy

### Enfoque dual: unit tests + property-based tests

**Unit tests** (pytest) para:
- Ejemplos concretos de filtrado de emergencias
- Comportamiento de fallback cuando la descarga falla
- Respuestas de endpoints FastAPI con datos mock de Supabase
- Casos borde: DataFrame vacío, todos los registros inválidos, GeoJSON sin features válidos

**Property-based tests** (Hypothesis) para las propiedades definidas en la sección anterior.

Configuración mínima:
```python
from hypothesis import given, settings
settings.register_profile("ci", max_examples=100)
settings.load_profile("ci")
```

Cada test de propiedad debe referenciar la propiedad del diseño:

```python
# Feature: medellin-landslide-risk, Property 1: Filtrado de eventos por tipo de emergencia
@given(st.dataframes(...))
def test_filter_keeps_only_landslide_events(df):
    result = filter_emergencies(df)
    assert all(
        "desliz" in row["tipo_emergencia"].lower() or
        "movimiento" in row["tipo_emergencia"].lower()
        for _, row in result.iterrows()
    )
```

### Cobertura por propiedad

| Propiedad | Tipo de test | Librería |
|-----------|-------------|----------|
| P1: Filtrado por tipo | property | Hypothesis |
| P2: Normalización fechas | property | Hypothesis |
| P3: Marcado sin coords | property | Hypothesis |
| P4: Precipitación inválida | property | Hypothesis |
| P5: Acumulados precipitación | property | Hypothesis |
| P6: Validación GeoJSON | property | Hypothesis |
| P7: Clasificación Zona_Ladera | property | Hypothesis |
| P8: Correlaciones Spearman | property | Hypothesis |
| P9: Cálculo índice de riesgo | property | Hypothesis |
| P10: Índice parcial | property | Hypothesis |
| P11: Alertas por umbral | property | Hypothesis |
| P12: Orden alertas | property | Hypothesis |
| P13: Persistencia alertas | example | pytest + mock Supabase |
| P14: Esquema CSV | property | Hypothesis |
| P15: Filtrado API events | property | Hypothesis |
| P16: Trazabilidad source_row_id | property | Hypothesis |
| P17: Esquema log calidad | example | pytest |

### Mocking de Supabase en tests

Para tests unitarios y de propiedad, se usa `unittest.mock` para evitar llamadas reales a Supabase:

```python
from unittest.mock import MagicMock, patch

@patch("app.supabase")
def test_risk_index_endpoint(mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = [...]
    # ...
```
