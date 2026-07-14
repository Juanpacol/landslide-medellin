# Gestión de Datos — TEYVA

## Estructura

```
data/
├── raw/        # Datos originales sin procesar descargados de las fuentes
├── processed/  # Datos limpios, transformados y listos para el modelo
├── realtime/   # Buffers de flujos en tiempo real (snapshots de APIs)
└── external/   # Datos auxiliares de terceros
```

## raw/
Datos abiertos tal como se descargan de las fuentes institucionales. No modificar manualmente.

- Archivos CSV/JSON de SIATA, DAGRD, IDEAM, GeoMedellín
- Dataset histórico de datos.gov.co (`emergencias_medellin_historico.csv`)
- **Excluido de git** — puede contener datos voluminosos (ver `.gitignore`)

## processed/
Datos tras el pipeline de limpieza y transformación (`notebooks/02_limpieza_transformacion.ipynb`):

- Valores nulos imputados
- Outliers tratados
- Variables normalizadas
- Ventanas temporales calculadas (1d, 3d, 7d)
- Listo para ingestar en `ml_features` o usar directamente en notebooks

## realtime/
Buffers temporales de los scrapers para flujos de datos en tiempo real:

- `siata_buffer.jsonl` — mediciones entrantes de SIATA (cada 30 min)
- `dagrd_buffer.jsonl` — eventos entrantes de DAGRD (cada 1 h)

Estos buffers se procesan y vacían hacia PostgreSQL por el scheduler.

## external/
Datos auxiliares que no provienen de las fuentes primarias:

- Polígonos GeoJSON de comunas (caché de ArcGIS)
- Shapefile de quebradas de Medellín
- Tablas de referencia de tipos de suelo

## Notas
- `raw/` está en `.gitignore`. Para el jurado: los datos se descargan automáticamente al correr `docker compose up` o los scrapers.
- El dataset de `datos.gov.co` puede descargarse manualmente desde `docs/fuentes_datos.md` y colocarse en `data/raw/`.
