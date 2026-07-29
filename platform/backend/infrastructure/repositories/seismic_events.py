"""
Repositorio de sismos: inserción deduplicada y agrupación en eventos canónicos.

Toda la lógica de "¿son el mismo sismo?" vive en `domain/seismic_dedup.py`, que
es puro y testeable sin base de datos. Aquí solo está el I/O.

Dos cosas que este módulo arregla del código anterior:

1. **N consultas → 1.** `scraper/siata_sismos.py` hacía un `SELECT` por fila para
   comprobar si el `source_row_id` ya existía. Con USGS y el SGC añadidos eso
   escala mal; `existing_source_row_ids` resuelve el lote en una sola consulta.
2. **Agrupación en clústeres.** Sin ella, cada sismo cuenta una vez por agencia
   en la Σ de magnitud² de `ml/seismic_features.py`, con inflado cuadrático.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.seismic_event import SeismicEvent
from db.models.seismic_event_cluster import SeismicEventCluster
from domain.seismic_dedup import (
    MATCH_TIME_WINDOW_S,
    EventKey,
    best_match,
    merge_sources,
    source_rank,
)


async def existing_source_row_ids(session: AsyncSession, source_row_ids: Iterable[str]) -> set[str]:
    """Cuáles de estos `source_row_id` ya están en la BD. UNA sola consulta."""
    ids = [i for i in source_row_ids if i]
    if not ids:
        return set()
    stmt = select(SeismicEvent.source_row_id).where(SeismicEvent.source_row_id.in_(ids))
    return set((await session.execute(stmt)).scalars().all())


async def insert_events(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> int:
    """Inserta reportes crudos ignorando los que ya existan. Devuelve los nuevos.

    Idempotente por construcción: `on_conflict_do_nothing` sobre el único
    `source_row_id`. Una corrida duplicada (cron + scheduler local a la vez)
    cuesta una fila en `scraping_logs`, nunca datos duplicados.

    Las filas se normalizan a un conjunto de claves COMÚN antes de insertar. Hace
    falta porque las fuentes son heterogéneas: SIATA trae `station_code` y
    `station_name`, USGS y el SGC no. En un INSERT multi-fila, SQLAlchemy exige
    que todos los dicts tengan las mismas claves; si no, falla con
    `CompileError: ... explicitly rendered as a boundparameter`, que no dice nada
    sobre la causa real.
    """
    if not rows:
        return 0

    keys: set[str] = set()
    for row in rows:
        keys |= set(row.keys())
    normalized = [{k: row.get(k) for k in keys} for row in rows]

    stmt = (
        pg_insert(SeismicEvent)
        .values(normalized)
        .on_conflict_do_nothing(index_elements=["source_row_id"])
        .returning(SeismicEvent.id)
    )
    return len((await session.execute(stmt)).scalars().all())


def _to_key(row: SeismicEvent | SeismicEventCluster) -> EventKey:
    """Adapta una fila de la BD al dataclass puro del dominio."""
    at = getattr(row, "event_at", None) or getattr(row, "event_local_at", None)
    return EventKey(
        event_at=at,  # type: ignore[arg-type]
        source=getattr(row, "canonical_source", None) or getattr(row, "source", ""),
        magnitude=row.magnitude,
        depth_km=row.depth_km,
        lat=row.epicenter_lat,
        lon=row.epicenter_lon,
        label=row.epicenter_label,
    )


async def _candidate_clusters(session: AsyncSession, at: datetime) -> list[SeismicEventCluster]:
    """Clústeres dentro de la ventana temporal de coincidencia (índice sobre
    `event_at`, así que son un puñado de filas)."""
    margin = timedelta(seconds=MATCH_TIME_WINDOW_S)
    stmt = select(SeismicEventCluster).where(
        SeismicEventCluster.event_at >= at - margin,
        SeismicEventCluster.event_at <= at + margin,
    )
    return list((await session.execute(stmt)).scalars().all())


async def assign_cluster(session: AsyncSession, event: SeismicEvent) -> int | None:
    """Asigna `event` a un clúster existente o crea uno. Devuelve el `cluster_id`.

    No hace commit: lo hace quien llama, para que la asignación viaje en la misma
    transacción que la inserción del reporte.

    Un evento sin `event_local_at` no se puede agrupar (el tiempo es la clave
    primaria de la coincidencia) y se deja con `cluster_id = NULL`.
    """
    if event.event_local_at is None:
        return None

    key = _to_key(event)
    candidates = await _candidate_clusters(session, event.event_local_at)
    idx = best_match(key, [_to_key(c) for c in candidates])

    if idx is None:
        cluster = SeismicEventCluster(
            event_at=event.event_local_at,
            magnitude=event.magnitude,
            mag_type=event.mag_type,
            depth_km=event.depth_km,
            epicenter_lat=event.epicenter_lat,
            epicenter_lon=event.epicenter_lon,
            epicenter_label=event.epicenter_label,
            canonical_source=event.source,
            sources=[event.source],
            source_count=1,
            member_count=1,
        )
        session.add(cluster)
        # flush (no commit) para obtener el id generado sin cerrar la transacción.
        await session.flush()
        event.cluster_id = cluster.id
        return cluster.id

    cluster = candidates[idx]
    cluster.member_count = (cluster.member_count or 0) + 1
    sources = merge_sources(list(cluster.sources or []), event.source)
    cluster.sources = sources
    cluster.source_count = len(sources)

    # Si la fuente nueva tiene MÁS autoridad, reemplaza los valores canónicos.
    # A igualdad de fuente no se toca nada: reprocesar no debe mover el consenso.
    if source_rank(event.source) < source_rank(cluster.canonical_source):
        cluster.event_at = event.event_local_at
        cluster.magnitude = event.magnitude
        cluster.mag_type = event.mag_type
        cluster.depth_km = event.depth_km
        cluster.epicenter_lat = event.epicenter_lat
        cluster.epicenter_lon = event.epicenter_lon
        cluster.epicenter_label = event.epicenter_label
        cluster.canonical_source = event.source

    event.cluster_id = cluster.id
    return cluster.id


async def recent_clusters(
    session: AsyncSession, since: datetime, *, until: datetime | None = None
) -> list[SeismicEventCluster]:
    """Sismos canónicos con magnitud conocida en una ventana.

    Esta es la superficie que consume `ml/seismic_features.py`: un sismo, una
    fila. Se filtra `magnitude IS NOT NULL` porque la intensidad es una Σ de
    magnitud² y una fila sin magnitud no aporta nada.
    """
    stmt = select(SeismicEventCluster).where(
        SeismicEventCluster.event_at >= since,
        SeismicEventCluster.magnitude.isnot(None),
    )
    if until is not None:
        stmt = stmt.where(SeismicEventCluster.event_at <= until)
    return list((await session.execute(stmt)).scalars().all())


async def unclustered_events(
    session: AsyncSession, *, limit: int = 1000, since: datetime | None = None
) -> list[SeismicEvent]:
    """Reportes todavía sin clúster, en orden cronológico.

    Los usa `scraper/seismic_cluster_backfill.py`. El orden importa: agrupar de
    más antiguo a más nuevo reproduce el orden en que habrían llegado.
    """
    stmt = (
        select(SeismicEvent)
        .where(
            SeismicEvent.cluster_id.is_(None),
            SeismicEvent.event_local_at.isnot(None),
        )
        .order_by(SeismicEvent.event_local_at.asc(), SeismicEvent.id.asc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(SeismicEvent.event_local_at >= since)
    return list((await session.execute(stmt)).scalars().all())
