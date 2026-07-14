# Fuentes de Datos

Documentación de todas las fuentes de datos abiertos utilizadas por TEYVA, sus URLs, licencias, frecuencia de actualización y variables consumidas.

---

## 1. SIATA — Sistema de Alerta Temprana de Medellín y el Valle de Aburrá

| Campo | Detalle |
|---|---|
| **Organización** | SIATA (Área Metropolitana del Valle de Aburrá) |
| **URL** | https://siata.gov.co |
| **Tipo de acceso** | API REST + archivos descargables |
| **Licencia** | Datos abiertos — uso libre con atribución |
| **Frecuencia de ingesta** | Cada 30 minutos |
| **Scraper** | `platform/backend/scraper/siata.py` |
| **Workflow** | `.github/workflows/scraper-siata.yml` |

**Variables consumidas:**
- `precip_mm` — Precipitación en milímetros por intervalo
- `humedad_suelo` — Humedad volumétrica del suelo (sensores geotécnicos)
- `temperatura_c` — Temperatura ambiente en °C
- `nivel_quebrada` — Nivel de quebradas monitoreadas

**Documentos adicionales consumidos:**
- Reportes semanales HIDROMET (PDFs vectorizados en RAG)
- Hojas de vida geotécnicas por zona (PDFs vectorizados en RAG)

---

## 2. DAGRD — Departamento Administrativo de Gestión del Riesgo de Desastres

| Campo | Detalle |
|---|---|
| **Organización** | Alcaldía de Medellín — DAGRD |
| **URL** | https://www.medellin.gov.co/es/dagrd |
| **Tipo de acceso** | Scraping web de reportes públicos |
| **Licencia** | Información pública institucional |
| **Frecuencia de ingesta** | Cada 1 hora |
| **Scraper** | `platform/backend/scraper/dagrd.py` |
| **Workflow** | `.github/workflows/scraper-dagrd.yml` |

**Variables consumidas:**
- `tipo_emergencia` — Clasificación del evento (deslizamiento, inundación, etc.)
- `barrio` / `comuna_id` — Ubicación del evento
- `fecha` — Fecha y hora del reporte
- `descripcion` — Texto libre del reporte oficial

---

## 3. IDEAM — Instituto de Hidrología, Meteorología y Estudios Ambientales

| Campo | Detalle |
|---|---|
| **Organización** | IDEAM — Gobierno de Colombia |
| **URL** | https://www.ideam.gov.co |
| **Tipo de acceso** | API REST |
| **Licencia** | Datos abiertos del Estado colombiano |
| **Frecuencia de ingesta** | Cada 6 horas |
| **Scraper** | `platform/backend/scraper/ideam.py` |
| **Workflow** | `.github/workflows/scraper-ideam.yml` |

**Variables consumidas:**
- `pronostico_lluvia` — Pronóstico de precipitación regional
- `velocidad_viento` — Velocidad del viento (km/h)
- `presion_atmosferica` — Presión en hPa
- `cobertura_nubosa` — Porcentaje de cobertura

---

## 4. GeoMedellín / ArcGIS — Información Geográfica de Medellín

| Campo | Detalle |
|---|---|
| **Organización** | Alcaldía de Medellín — Departamento de Planeación |
| **URL** | https://geomedellin-m-medellin.opendata.arcgis.com |
| **Tipo de acceso** | ArcGIS REST API |
| **Licencia** | Datos abiertos — Creative Commons |
| **Frecuencia de ingesta** | Cada 24 horas |
| **Scraper** | `platform/backend/scraper/medellin_datos.py` |
| **Workflow** | `.github/workflows/scraper-medellin.yml` |
| **Cliente** | `platform/backend/infrastructure/external/arcgis.py` |

**Variables consumidas:**
- `poligono_geojson` — Polígono GeoJSON de cada comuna
- `pendiente_promedio` — Pendiente media del terreno (grados)
- `uso_suelo` — Clasificación de uso del suelo
- `cobertura_vegetal` — Tipo y densidad de cobertura
- `centroid_lat` / `centroid_lon` — Centroide de la comuna

---

## 5. Red Sismológica — SIATA Sismos

| Campo | Detalle |
|---|---|
| **Organización** | SIATA |
| **Frecuencia de ingesta** | Cada 30 minutos |
| **Scraper** | `platform/backend/scraper/` (sismos) |
| **Workflow** | `.github/workflows/scraper-siata-sismos.yml` |

**Variables consumidas:**
- `magnitud` — Magnitud Richter
- `profundidad_km` — Profundidad del sismo
- `lat` / `lon` — Epicentro
- `distancia_medellin_km` — Distancia calculada al centroide de Medellín

---

## 6. datos.gov.co — Portal de Datos Abiertos del Estado

| Campo | Detalle |
|---|---|
| **URL** | https://www.datos.gov.co |
| **Uso** | Dataset histórico de emergencias y eventos de deslizamiento para entrenamiento inicial del modelo |
| **Licencia** | Creative Commons Attribution 4.0 |

Dataset descargado almacenado en `data/raw/`.

---

## Notas de implementación

- Todos los scrapers usan deduplicación por `source_row_id` — un registro con el mismo ID nunca se inserta dos veces.
- `records_valid=0` con `status=ok` significa "sin registros nuevos", no error.
- GitHub Actions puede deshabilitar crons automáticamente tras 60 días sin commits (`disabled_inactivity`). Verificar con `gh workflow list` si las fuentes parecen caídas.
- El watchdog del scheduler (`scraper/scheduler.py`) alerta vía Slack si una fuente lleva más de 3× su intervalo sin datos.
