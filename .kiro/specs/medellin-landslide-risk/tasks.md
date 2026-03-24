# Plan de Implementación: Sistema de Análisis de Riesgo de Deslizamientos — Medellín

## Overview

Flujo simple: recopilar datos de 3 fuentes → ETL → cargar a Supabase → API → frontend.

Stack: Python 3.11 + FastAPI + supabase-py + pandas + requests. Frontend: HTML + Vanilla JS + Leaflet.js + Chart.js.

## Tasks

- [x] 1. Setup del proyecto
  - Crear `requirements.txt` con: fastapi, uvicorn, supabase, python-dotenv, pandas, requests, httpx
  - Crear `.env.example` con `SUPABASE_URL=` y `SUPABASE_KEY=`
  - Crear `.gitignore` que excluya `.env`, `data/raw/`, `__pycache__/`
  - Crear `setup_db.sql` con los `CREATE TABLE` de las 5 tablas: `events`, `precipitation`, `communes`, `alerts`, `data_quality_log`
  - _Requirements: 10.1, 10.4_

- [x] 2. ETL — Recopilar y limpiar datos de las 3 fuentes en `etl.py`
  - [x] 2.1 Fuente 1: Emergencias (medata.gov.co)
    - Descargar CSV desde `https://medata.gov.co/dataset/emergencias-atendidas-cuerpo-oficial-bomberos`
    - Filtrar registros donde `tipo_emergencia` contenga 'desliz' o 'movimiento' (sin distinción de mayúsculas)
    - Normalizar campo `fecha` a ISO 8601, marcar `has_coords=False` si faltan latitud/longitud, asignar `source_row_id`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

  - [x] 2.2 Fuente 2: Precipitación (datos.gov.co)
    - Descargar CSV desde `https://www.datos.gov.co/dataset/precipitacion-diaria-colombia` filtrando `cod_municipio=05001`
    - Descartar registros con `precipitacion_mm` negativo o no numérico
    - Calcular `precipitacion_acum_3d` y `precipitacion_acum_7d` con rolling sum ordenado por fecha
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.3 Fuente 3: GeoJSON comunas (GeoMedellín)
    - Descargar GeoJSON desde `https://geomedellin-m-medellin.opendata.arcgis.com/`
    - Validar que cada feature tenga `commune_id`, `nombre_comuna` y `geometry` de tipo Polygon o MultiPolygon
    - Omitir features inválidos; clasificar `is_zona_ladera=True` si `pendiente_promedio >= 15`
    - _Requirements: 3.1, 3.2, 3.3, 3.6_

  - [x] 2.4 Registrar log de calidad de datos
    - Por cada fuente, registrar en `data_quality_log`: registros descargados, válidos, descartados, motivo y estado (OK/Error)
    - Si una descarga falla, registrar error y continuar con datos existentes en Supabase
    - _Requirements: 1.5, 10.1, 10.5_

- [x] 3. Cargar datos limpios a Supabase en `etl.py`
  - [x] 3.1 Insertar eventos y precipitación
    - `upsert` de registros de `events` y `precipitation` usando supabase-py
    - Validar que `SUPABASE_URL` y `SUPABASE_KEY` estén definidas; fallar con mensaje claro si no
    - _Requirements: 1.5, 2.2, 11.5_

  - [x] 3.2 Insertar comunas y log de calidad
    - `upsert` de `communes` (reemplaza en cada ejecución) e insert de `data_quality_log`
    - _Requirements: 3.4, 10.1, 10.4_

- [x] 4. Calcular índice de riesgo y alertas en `etl.py`
  - [x] 4.1 Calcular correlaciones e índice de riesgo por comuna
    - Correlación de Spearman entre precipitación y frecuencia de eventos (solo comunas con >= 10 eventos)
    - Índice de riesgo: frecuencia (0.4) + precipitación acum 7d (0.4) + pendiente (0.2), normalizado [0,1]
    - Si falta pendiente: usar frecuencia (0.5) + precipitación (0.5), marcar `indice_parcial=True`
    - Clasificar en Bajo/Medio/Alto/Crítico y guardar en tabla `communes`
    - _Requirements: 4.1, 4.2, 4.5, 5.1, 5.2, 5.3, 5.4_

  - [x] 4.2 Evaluar alertas por umbral de precipitación
    - Alerta Naranja si `precipitacion_mm > 50` en Zona_Ladera
    - Alerta Roja si `precipitacion_acum_3d > 100` en Zona_Ladera
    - Guardar alertas en tabla `alerts` con `commune_id`, `nivel`, `precipitacion_valor`, `tipo_umbral`, `timestamp`
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

- [x] 5. API FastAPI mínima en `app.py`
  - [x] 5.1 Configurar app y conexión Supabase
    - Inicializar FastAPI, cargar `.env`, crear cliente supabase-py
    - Montar archivos estáticos desde `static/`; retornar HTTP 503 si Supabase no disponible
    - _Requirements: 9.4, 11.4_

  - [x] 5.2 Implementar los 4 endpoints necesarios
    - `GET /` → sirve `index.html`
    - `GET /api/export/geojson` → GeoJSON de comunas con `categoria_riesgo` e `indice_riesgo` (para el mapa)
    - `GET /api/events` → eventos filtrados por `commune_id` (para la serie de tiempo)
    - `GET /api/alerts` → alertas activas ordenadas Rojo primero (para el banner)
    - _Requirements: 6.1, 7.1, 8.4, 9.2_

- [ ] 6. Frontend en `static/`
  - [ ] 6.1 Crear `static/index.html` y `static/style.css`
    - Layout: banner de alertas arriba, mapa a la izquierda, panel lateral de detalle a la derecha, gráfica abajo
    - Colores de riesgo: verde (Bajo), amarillo (Medio), naranja (Alto), rojo (Crítico)
    - _Requirements: 6.1, 6.2, 8.4_

  - [ ] 6.2 Gráfico 1 — Mapa coroplético Leaflet en `static/app.js`
    - Cargar GeoJSON desde `/api/export/geojson`, colorear polígonos por `categoria_riesgo`
    - Al hacer clic en una comuna: mostrar en panel lateral el nombre, nivel de riesgo, número de deslizamientos y si es zona de ladera
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ] 6.3 Gráfico 2 — Serie de tiempo doble eje en `static/app.js`
    - Barras azules: precipitación diaria (mm) — eje Y izquierdo
    - Línea roja: frecuencia de deslizamientos por día — eje Y derecho
    - Se actualiza al seleccionar una comuna en el mapa; título claro: "Lluvia vs Deslizamientos"
    - Banner de alertas activas desde `/api/alerts` (Rojo primero)
    - _Requirements: 7.1, 7.2, 8.4, 8.5_
