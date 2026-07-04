-- Eventos de deslizamiento filtrados
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    source_row_id   TEXT,
    fecha           TEXT,
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
    categoria_riesgo    TEXT,
    indice_parcial      BOOLEAN,
    n_eventos           INTEGER,
    correlacion_diaria  REAL,
    correlacion_3d      REAL,
    correlacion_7d      REAL,
    geometry            TEXT
);

-- Alertas generadas
CREATE TABLE alerts (
    id                  BIGSERIAL PRIMARY KEY,
    commune_id          TEXT,
    nivel               TEXT,
    precipitacion_valor REAL,
    tipo_umbral         TEXT,
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
    estado                TEXT
);
