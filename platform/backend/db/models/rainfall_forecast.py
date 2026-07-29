from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class RainfallForecast(Base):
    """Pronóstico de lluvia por comuna y día objetivo. APPEND-ONLY.

    Tabla separada de `rainfall_timeseries` porque un pronóstico no es una
    observación, y tratarlo como tal rompe tres cosas concretas: la suma sin
    filtro de `infrastructure/repositories/rainfall.py` que alimenta la alerta
    Slack (alertas rojas falsas), la lluvia ANTECEDENTE de `ml/precip_index.py` y
    `ml/soil_water_index.py` (un pronóstico no es antecedente), y el chequeo
    `future_timestamps` de `monitoring/scraper_validator.py`.

    Y tiene una dimensión que la tabla observada no admite:
    **(issued_at, target_date)**. El mismo día objetivo se re-pronostica en cada
    corrida; "el último pronóstico para D+3" no se expresa con una bandera. Las
    lecturas usan `DISTINCT ON (commune_id, target_date) ORDER BY issued_at DESC`.

    Nunca se sobreescribe un pronóstico ya emitido: en 12-18 meses esta tabla ES
    el archivo de pronósticos, y es lo único que permitiría convertir el
    pronóstico en feature de entrenamiento sin filtrar la etiqueta (hoy la
    etiqueta es "evento en (ref_d, ref_d+7d]", así que la lluvia futura no
    correlaciona con ella: la CAUSA).
    """

    __tablename__ = "rainfall_forecast"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commune_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Truncado al minuto por quien escribe. Un now() sin truncar haría que cada
    # corrida duplicada (cron + scheduler local) inserte filas nuevas en vez de
    # chocar con el índice único: es el único punto donde un timestamp
    # descuidado rompe la idempotencia de toda la ingesta.
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    precip_mm: Mapped[float] = mapped_column(Float, nullable=False)
    # Probabilidad de precipitación (`pop` de OWM, 0..1). Nullable: no toda
    # fuente la entrega.
    precip_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_rainfall_forecast_unique",
            "commune_id",
            "target_date",
            "issued_at",
            "source",
            unique=True,
        ),
        Index("ix_rainfall_forecast_lookup", "commune_id", "target_date"),
    )
