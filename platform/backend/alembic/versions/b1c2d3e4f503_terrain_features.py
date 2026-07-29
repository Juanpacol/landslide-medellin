"""terreno sub-comuna: barrio_terrain + columnas de susceptibilidad en mesh_quadrants

Soporte para pendiente (DEM SRTM), Índice de Humedad Topográfico (TWI, derivado
del DEM) y cobertura vegetal (NDVI, MODIS).

**Por qué a nivel de barrio y no de comuna.** Con 26 eventos positivos y 21
comunas, una variable de terreno por comuna es una constante por comuna: el
modelo la usaría como identificador, igual que hacía con `centroid_lat/lon`.
A nivel de barrio (401 polígonos en `platform/frontend/lib/barrios-medellin.json`,
la misma base que ya usan `barrio_hazard` y `mesh_quadrants`) las variables sí
varían de verdad, y se agregan a la comuna como percentiles.

**Por qué p90 y no la media.** El promedio de un barrio con una ladera empinada y
una zona plana es engañoso — el deslizamiento ocurre en la ladera. Se guardan
ambos: la media para contexto y el p90 para la señal.

**Nada de esto lo puebla la migración.** Los valores los escribe
`scraper/terrain_features.py`, un script puntual que lee GeoTIFF descargados a
mano (la topografía cambia en décadas; el NDVI, por temporada). Por eso todas las
columnas son nullable: la tabla existe vacía y se llena cuando haya datos.

Nota sobre `barrio_hazard`, descubierta al preparar esto: de los 401 polígonos,
**132 son de Bello** (`properties.comuna == "B"`), otro municipio, y se guardan
con `commune_id="B"`. Además los 5 corregimientos (ids 17-21) no tienen ningún
barrio en ese GeoJSON, así que `pct_barrios_alta_amenaza` no existe justo para
los 5 territorios que son todos ladera. No se corrige aquí (es un cambio de
ingesta, no de esquema), pero queda anotado.

Revision ID: b1c2d3e4f503
Revises: b1c2d3e4f502
Create Date: 2026-07-29 16:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f503"
down_revision: Union[str, None] = "b1c2d3e4f502"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MESH_COLUMNS = (
    "slope_p90_deg",
    "twi_p90",
    "ndvi_mean",
    "susceptibility_index",
    "susceptibility_grade",
)


def upgrade() -> None:
    op.create_table(
        "barrio_terrain",
        # Misma PK que barrio_hazard: se unen por barrio_codigo.
        sa.Column("barrio_codigo", sa.String(length=32), nullable=False),
        sa.Column("commune_id", sa.String(length=64), nullable=True),
        # ── Pendiente, en GRADOS (no porcentaje) ──────────────────────────────
        sa.Column("slope_mean_deg", sa.Float(), nullable=True),
        sa.Column("slope_p90_deg", sa.Float(), nullable=True),
        # ── TWI = ln(a / tan β). Adimensional, típicamente ~1-30 ──────────────
        # Ojo al implementarlo: tan β → 0 en terreno plano hace explotar el TWI.
        # Hay que acotar β a un mínimo (p. ej. 0.001 rad) y documentarlo.
        sa.Column("twi_mean", sa.Float(), nullable=True),
        sa.Column("twi_p90", sa.Float(), nullable=True),
        # ── NDVI = (NIR − Red)/(NIR + Red), rango [-1, 1] ─────────────────────
        # ndvi_min es la señal útil: la vegetación MÍNIMA es la que deja el
        # suelo desnudo y sin raíces que estabilicen la ladera.
        sa.Column("ndvi_mean", sa.Float(), nullable=True),
        sa.Column("ndvi_min", sa.Float(), nullable=True),
        sa.Column("elevation_mean_m", sa.Float(), nullable=True),
        # Procedencia: qué DEM y qué producto NDVI generaron estos valores.
        sa.Column("dem_source", sa.String(length=32), nullable=True),
        sa.Column("ndvi_source", sa.String(length=32), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("barrio_codigo"),
    )
    op.create_index("ix_barrio_terrain_commune_id", "barrio_terrain", ["commune_id"])

    # ── mesh_quadrants: agregados heredados de sus barrios ────────────────────
    # Esto le da a la malla su PROPIA señal por primera vez. Su docstring admite
    # hoy que "el riesgo de cada cuadrícula se HEREDA del modelo a nivel comuna";
    # con terreno por cuadrante deja de ser pura herencia.
    op.add_column("mesh_quadrants", sa.Column("slope_p90_deg", sa.Float(), nullable=True))
    op.add_column("mesh_quadrants", sa.Column("twi_p90", sa.Float(), nullable=True))
    op.add_column("mesh_quadrants", sa.Column("ndvi_mean", sa.Float(), nullable=True))
    op.add_column("mesh_quadrants", sa.Column("susceptibility_index", sa.Float(), nullable=True))
    op.add_column(
        "mesh_quadrants", sa.Column("susceptibility_grade", sa.String(length=32), nullable=True)
    )

    op.execute('ALTER TABLE public."barrio_terrain" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.execute('ALTER TABLE public."barrio_terrain" DISABLE ROW LEVEL SECURITY')
    for col in _MESH_COLUMNS:
        op.drop_column("mesh_quadrants", col)
    op.drop_index("ix_barrio_terrain_commune_id", table_name="barrio_terrain")
    op.drop_table("barrio_terrain")
