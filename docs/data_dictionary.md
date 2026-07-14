# Diccionario de Datos — TEYVA

Definición de las variables del consolidado utilizado para entrenamiento y predicción.

---

## Tabla `ml_features` — Features por comuna y fecha

| Variable | Tipo | Fuente | Descripción | Rango esperado |
|---|---|---|---|---|
| `commune_id` | str | GeoMedellín | ID canónico de la comuna ("1"–"21") | "1" a "21" |
| `feature_date` | date | calculado | Fecha del registro de features | — |
| `precip_1d_mm` | float | SIATA | Precipitación acumulada últimas 24 h (mm) | 0 – 200 |
| `precip_3d_mm` | float | SIATA | Precipitación acumulada últimas 72 h (mm) | 0 – 400 |
| `precip_7d_mm` | float | SIATA | Precipitación acumulada últimos 7 días (mm) | 0 – 800 |
| `precip_pico_mm` | float | SIATA | Pico máximo en una sola medición (30 min) | 0 – 80 |
| `dias_lluvia_consecutivos` | int | SIATA | Días consecutivos con precipitación > 5 mm | 0 – 30 |
| `humedad_suelo_pct` | float | SIATA | Humedad volumétrica del suelo (%) | 0 – 100 |
| `temperatura_min_c` | float | SIATA/IDEAM | Temperatura mínima del período (°C) | 5 – 30 |
| `n_events_30d` | int | DAGRD | Eventos de deslizamiento en los últimos 30 días | 0 – 50 |
| `n_events_90d` | int | DAGRD | Eventos de deslizamiento en los últimos 90 días | 0 – 150 |
| `pendiente_promedio` | float | GeoMedellín | Pendiente media del terreno de la comuna (grados) | 0 – 45 |
| `uso_suelo_encoded` | int | GeoMedellín | Clasificación de uso del suelo (label encoding) | 0 – 8 |
| `cobertura_vegetal_pct` | float | GeoMedellín | Porcentaje de cobertura vegetal | 0 – 100 |
| `centroid_lat` | float | GeoMedellín | Latitud del centroide de la comuna | 6.15 – 6.35 |
| `centroid_lon` | float | GeoMedellín | Longitud del centroide de la comuna | -75.65 – -75.50 |
| `sismo_mag_max_7d` | float | SIATA Sismos | Magnitud máxima de sismo en 7 días cercano | 0 – 6 |
| `pronostico_lluvia_mm` | float | IDEAM | Pronóstico de precipitación próximas 48 h | 0 – 150 |

---

## Tabla `landslide_events` — Eventos históricos de deslizamiento

| Variable | Tipo | Fuente | Descripción |
|---|---|---|---|
| `id` | int | BD | Identificador interno |
| `commune_id` | str | DAGRD/geocodificado | ID de la comuna donde ocurrió el evento |
| `barrio` | str | DAGRD | Barrio reportado |
| `fecha` | date | DAGRD | Fecha del evento |
| `tipo_emergencia` | str | DAGRD | Clasificación: "deslizamiento", "movimiento_masa", etc. |
| `descripcion` | text | DAGRD | Texto libre del reporte oficial |
| `is_synthetic` | bool | sistema | `true` si fue generado por Snake Line (excluido del ML) |
| `ingested_at` | datetime | sistema | Timestamp de ingesta |

---

## Tabla `risk_predictions` — Salida del modelo ML

| Variable | Tipo | Descripción |
|---|---|---|
| `commune_id` | str | ID de la comuna |
| `risk_score` | float | Probabilidad de deslizamiento (0.0 – 1.0) |
| `risk_category` | str | Nivel: `bajo`, `medio`, `alto`, `critico` |
| `model_version` | str | Hash git + timestamp del modelo usado |
| `created_at` | datetime | Timestamp de la predicción |

**Umbrales de categorización** (definidos en `domain/risk_rules.py`):
- bajo: score < 0.35
- medio: 0.35 ≤ score < 0.65
- alto: 0.65 ≤ score < 0.90
- crítico: score ≥ 0.90

---

## Tabla `rainfall_timeseries` — Serie temporal de lluvia

| Variable | Tipo | Descripción |
|---|---|---|
| `commune_id` | str | ID de la comuna |
| `precip_mm` | float | Precipitación en el intervalo (mm) |
| `snapshot_at` | datetime | Timestamp de la medición SIATA |

---

## Tabla `citizen_reports` — Reportes ciudadanos

| Variable | Tipo | Descripción |
|---|---|---|
| `commune_id` | str | Comuna reportada |
| `barrio` | str | Barrio (opcional) |
| `descripcion` | text | Descripción del ciudadano (máx. 2,000 caracteres) |
| `status` | str | `pending_review` → `verified` / `discarded` |
| `session_id` | str | ID de sesión del chat que originó el reporte |
| `created_at` | datetime | Timestamp del reporte |

---

## Notas de calidad de datos

- **Valores nulos:** la imputación usa la mediana de ventana 7 días por comuna. Si no hay datos suficientes, el registro se excluye del entrenamiento pero no de la predicción (se usa el último valor conocido).
- **Outliers de precipitación:** valores > percentil 99.5 se winsorize a ese límite antes del entrenamiento.
- **Deduplicación:** todos los scrapers usan `source_row_id` como clave natural — inserciones idempotentes.
- **Zona horaria:** todos los timestamps en UTC. La conversión a hora local (UTC-5 Colombia) es responsabilidad del frontend.
