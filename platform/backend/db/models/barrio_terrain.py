from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class BarrioTerrain(Base):
    """Variables de terreno por BARRIO: pendiente, TWI y NDVI.

    Poblada por `scraper/terrain_features.py` (script puntual) desde GeoTIFF
    descargados a mano: DEM de SRTM y NDVI de MODIS. Todo nullable porque la
    tabla existe vacía hasta que haya datos.

    **Por qué a nivel de barrio.** Con 26 eventos positivos y 21 comunas, una
    variable de terreno por comuna es una constante por comuna: el modelo la
    usaría como identificador, igual que hacía con `centroid_lat`/`centroid_lon`.
    Sobre los 401 barrios (misma base que `barrio_hazard` y `mesh_quadrants`) sí
    varían de verdad, y se agregan a comuna como percentiles.

    **Por qué p90 además de la media.** El promedio de un barrio con una ladera
    empinada y una zona plana es engañoso: el deslizamiento ocurre en la ladera.

    Estas variables NO entran al modelo como columnas sueltas; se combinan en
    `domain/susceptibility.py` con pesos documentados (amenaza = susceptibilidad
    × disparador). El dashboard sí muestra cada capa por separado.
    """

    __tablename__ = "barrio_terrain"

    barrio_codigo: Mapped[str] = mapped_column(String(32), primary_key=True)
    commune_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Pendiente en GRADOS (no porcentaje).
    slope_mean_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    slope_p90_deg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # TWI = ln(a / tan β), adimensional, típicamente ~1-30. Cuidado al
    # calcularlo: tan β → 0 en terreno plano hace explotar el índice, así que β
    # se acota a un mínimo (p. ej. 0.001 rad).
    twi_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    twi_p90: Mapped[float | None] = mapped_column(Float, nullable=True)

    # NDVI = (NIR − Red)/(NIR + Red), rango [-1, 1]. `ndvi_min` es la señal útil:
    # la vegetación MÍNIMA es la que deja suelo desnudo, sin raíces que
    # estabilicen la ladera.
    ndvi_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_min: Mapped[float | None] = mapped_column(Float, nullable=True)

    elevation_mean_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Procedencia: qué DEM y qué producto NDVI generaron estos valores.
    dem_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ndvi_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_barrio_terrain_commune_id", "commune_id"),)
