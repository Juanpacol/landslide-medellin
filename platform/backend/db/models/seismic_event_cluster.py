from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SeismicEventCluster(Base):
    """Un sismo FÍSICO, agrupando lo que reportan SIATA, USGS y el SGC.

    Esta tabla es la superficie que consume el ML: `ml/seismic_features.py` lee
    clústeres, no filas crudas, así que la heurística de deduplicación
    desaparece del código de features.

    **El problema que resuelve.** Un mismo sismo genera K filas en
    `seismic_events` (una por estación SIATA que lo registró) más una por cada
    agencia. La deduplicación anterior era por
    `(event_local_at.isoformat(), epicenter_label)`, que solo funciona dentro de
    SIATA: entre agencias los tiempos de origen difieren en segundos y las
    etiquetas son textos distintos, así que ningún duplicado colapsaría. Y como
    la feature es una **Σ de magnitud²**, cada sismo contaría 2-3 veces y la
    señal se inflaría de forma cuadrática, en silencio.

    Las filas crudas de `seismic_events` nunca se borran ni se mutan: los números
    de cada agencia quedan auditables. Este clúster es la lectura de consenso.

    Reglas de agrupación y tolerancias: `domain/seismic_dedup.py` (puro).
    """

    __tablename__ = "seismic_event_clusters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Tiempo de origen de consenso (UTC), del ganador de precedencia.
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Magnitud de consenso = la del ganador de precedencia. NO el máximo (sesga
    # al alza, y la feature eleva al cuadrado, así que amplifica el sesgo) ni la
    # media (mezcla escalas incompatibles: ML vs Mw vs Mb difieren 0.3-0.7).
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Escala de la magnitud canónica. El SGC publica `MLr*` y USGS `mb`: son
    # escalas DISTINTAS y no comparables, así que guardar el número sin la escala
    # invitaría a promediarlas. Es otra razón por la que el consenso es "el valor
    # del ganador de precedencia" y no una media.
    mag_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    depth_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Qué fuente ganó la precedencia (SGC > USGS > SIATA) → trazabilidad.
    canonical_source: Mapped[str] = mapped_column(String(32), nullable=False)
    # ["siata_sismos", "usgs"] — permite responder "confirmado por 3 agencias"
    # sin un GROUP BY, y matizar la confianza de una alerta.
    sources: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=func.cast("[]", JSONB)
    )
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # Incluye las K filas de estación de SIATA; source_count no.
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # La búsqueda de candidatos es una ventana de ±120 s sobre event_at.
    __table_args__ = (Index("ix_seismic_clusters_event_at", "event_at"),)
