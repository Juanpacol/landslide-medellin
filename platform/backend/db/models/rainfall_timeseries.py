from sqlalchemy import BigInteger, Column, DateTime, Float, Index, Integer, String

from db.base import Base


class RainfallTimeseries(Base):
    """Snapshots de lluvia OBSERVADA (grano de 30 min para SIATA).

    Los totales DIARIOS de otras fuentes (GPM, CHIRPS, IDEAM) no van aquí sino en
    `daily_precipitation`: mezclar granos rompería `GET /api/rain/live`, que suma
    `precip_mm` por snapshot. La excepción es `owm_observed`, que se escribe aquí
    solo como relleno y solo cuando ese (comuna, día) no tiene ya filas de SIATA
    — si no, la suma diaria contaría la lluvia dos veces.

    El pronóstico va en `rainfall_forecast`, nunca aquí: esta tabla la suman sin
    filtro la alerta Slack de umbral y los índices de lluvia antecedente.
    """

    __tablename__ = "rainfall_timeseries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    commune_id = Column(String(64), nullable=False)
    snapshot_at = Column(DateTime(timezone=True), nullable=False)
    precip_mm = Column(Float, nullable=False)
    station_count = Column(Integer, nullable=True)
    # "siata" (30 min, red local) | "owm_observed" (relleno cuando SIATA cae o
    # la comuna no tiene estación). Ver docstring de la clase.
    source = Column(String(32), nullable=False, server_default="siata")

    __table_args__ = (
        # El índice único INCLUYE `source` a propósito. Con solo
        # (commune_id, snapshot_at), una fila de OWM que coincidiera en
        # `snapshot_at` con una de SIATA se la tragaría en silencio el
        # `on_conflict_do_nothing` de `scraper/siata.py`: sin error, sin
        # excepción y sin contarla como descartada.
        Index(
            "ix_rainfall_ts_commune_snap_src", "commune_id", "snapshot_at", "source", unique=True
        ),
        Index("ix_rainfall_ts_source", "source"),
    )
