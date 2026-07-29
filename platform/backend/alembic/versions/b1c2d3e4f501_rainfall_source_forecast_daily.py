"""lluvia multi-fuente: rainfall_timeseries.source + daily_precipitation + rainfall_forecast

Prepara la entrada de OpenWeatherMap (relleno de observación + pronóstico) y del
histórico satelital (GPM/CHIRPS) sin corromper lo que ya funciona.

Tres decisiones que conviene entender antes de tocar esto:

1. **El índice único de `rainfall_timeseries` se AMPLÍA a incluir `source`.**
   Era `(commune_id, snapshot_at)`. Si se añade `source` sin ampliarlo, una fila
   de OWM con el mismo `snapshot_at` que una de SIATA se la traga en silencio el
   `on_conflict_do_nothing` de `scraper/siata.py` — sin error, sin excepción y
   sin contarla como descartada. Un dato que desaparece sin rastro es peor que
   un fallo ruidoso.

2. **`daily_precipitation` es una tabla NUEVA, no filas más en
   `rainfall_timeseries`.** SIATA escribe ~48 snapshots de 30 min por comuna y
   día; un total diario de OWM/GPM/CHIRPS es UNA cifra para el mismo día.
   Mezclar ambos granos en la misma tabla rompería `GET /api/rain/live`, que
   suma `precip_mm` por snapshot. La resolución de qué fuente gana para cada
   (comuna, día) vive en `infrastructure/repositories/daily_rain.py`, con una
   escalera de precedencia y un invariante: jamás se suman dos fuentes para el
   mismo (comuna, día).

3. **El pronóstico va en su propia tabla, NO en una bandera `is_forecast`.**
   Razones concretas, no de estilo:
   - `infrastructure/repositories/rainfall.py::accumulated_since_by_commune`
     suma la tabla SIN filtro y alimenta la alerta Slack de umbral → filas de
     pronóstico producirían alertas rojas falsas.
   - `ml/precip_index.py` y `ml/soil_water_index.py` agregan esa misma tabla
     para lluvia ANTECEDENTE; un pronóstico no es antecedente por definición.
   - `monitoring/scraper_validator.py` marca `snapshot_at > now` como
     `future_timestamps` → cada fila de pronóstico sería un aviso del validador.
   - Y el pronóstico tiene una dimensión que la tabla observada no admite:
     **(issued_at, target_date)**. El mismo día objetivo se re-pronostica en
     cada corrida; "el último pronóstico para D+3" no se puede expresar con una
     bandera.
   `rainfall_forecast` es APPEND-ONLY: nunca se sobreescribe un pronóstico ya
   emitido. En 12-18 meses esa tabla es el archivo de pronósticos, que es lo
   único que permitiría usar el pronóstico como feature de entrenamiento sin
   filtrar la etiqueta.

Revision ID: b1c2d3e4f501
Revises: a1b2c3d4e5f6
Create Date: 2026-07-29 16:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f501"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = ("daily_precipitation", "rainfall_forecast")


def upgrade() -> None:
    # ── rainfall_timeseries: columna source + índice único ampliado ───────────
    # server_default deja todas las filas existentes como 'siata', que es lo que
    # son. No hace falta un UPDATE de backfill.
    op.add_column(
        "rainfall_timeseries",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="siata"),
    )
    op.drop_index("ix_rainfall_ts_commune_snap", table_name="rainfall_timeseries")
    op.create_index(
        "ix_rainfall_ts_commune_snap_src",
        "rainfall_timeseries",
        ["commune_id", "snapshot_at", "source"],
        unique=True,
    )
    op.create_index("ix_rainfall_ts_source", "rainfall_timeseries", ["source"])

    # ── daily_precipitation: grano DIARIO, una fila por (comuna, día, fuente) ─
    op.create_table(
        "daily_precipitation",
        sa.Column("commune_id", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("precip_mm", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # PK compuesta: la precedencia entre fuentes se resuelve al LEER, no al
        # escribir, así que conviven varias fuentes para el mismo día.
        sa.PrimaryKeyConstraint("commune_id", "day", "source"),
    )
    op.create_index("ix_daily_precip_day", "daily_precipitation", ["day"])

    # ── rainfall_forecast: append-only, (issued_at, target_date) ──────────────
    op.create_table(
        "rainfall_forecast",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("commune_id", sa.String(length=64), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        # Truncado al minuto por quien escribe: un now() sin truncar haría que
        # cada corrida duplicada inserte filas nuevas y rompa la idempotencia.
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("precip_mm", sa.Float(), nullable=False),
        # Probabilidad de precipitación (`pop` de OWM, 0..1). Útil para matizar
        # la confianza de una alerta; nullable porque no toda fuente la da.
        sa.Column("precip_prob", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rainfall_forecast_unique",
        "rainfall_forecast",
        ["commune_id", "target_date", "issued_at", "source"],
        unique=True,
    )
    op.create_index(
        "ix_rainfall_forecast_lookup", "rainfall_forecast", ["commune_id", "target_date"]
    )

    # RLS, igual que el resto de tablas públicas (revisión a1b2c3d4e5f6): sin
    # policies, para que nadie las lea por la API REST autogenerada de Supabase.
    for table in _NEW_TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in _NEW_TABLES:
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')

    op.drop_index("ix_rainfall_forecast_lookup", table_name="rainfall_forecast")
    op.drop_index("ix_rainfall_forecast_unique", table_name="rainfall_forecast")
    op.drop_table("rainfall_forecast")

    op.drop_index("ix_daily_precip_day", table_name="daily_precipitation")
    op.drop_table("daily_precipitation")

    # IMPORTANTE: recrear el índice único de 2 columnas falla si ya existen
    # filas de otra fuente que dupliquen un (commune_id, snapshot_at). Se
    # eliminan primero — es un downgrade, la pérdida de datos no-SIATA es
    # deliberada y es el único modo de que la operación sea reversible.
    op.execute("DELETE FROM rainfall_timeseries WHERE source <> 'siata'")
    op.drop_index("ix_rainfall_ts_source", table_name="rainfall_timeseries")
    op.drop_index("ix_rainfall_ts_commune_snap_src", table_name="rainfall_timeseries")
    op.create_index(
        "ix_rainfall_ts_commune_snap",
        "rainfall_timeseries",
        ["commune_id", "snapshot_at"],
        unique=True,
    )
    op.drop_column("rainfall_timeseries", "source")
