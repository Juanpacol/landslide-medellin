"""
Scraper de sismos del Servicio Geológico Colombiano.

Sustituye a SIATA como fuente sísmica PRIMARIA. Motivos medidos el 2026-07-29:

- El feed de SIATA lleva sin producir eventos nuevos desde el 2026-03-01 —150
  días— mientras el scraper reporta `ok` en cada corrida, porque
  `records_valid=0` significa "sin eventos nuevos" y es indistinguible de "el
  parser dejó de encajar". `monitoring/scraper_validator.py` ahora lo detecta.
- En 7 días el SGC publicó **35 sismos** dentro del bounding box del Valle de
  Aburrá. SIATA, cero.
- USGS no sirve como primario: en julio 2026 completo y sin umbral de magnitud
  devolvió **0 eventos** en ese mismo bbox.

Cada fila se agrupa en un evento canónico (`seismic_event_clusters`) nada más
insertarse, dentro de la misma transacción. Sin eso, el mismo sismo reportado por
SIATA, USGS y el SGC contaría tres veces en la Σ de magnitud² de
`ml/seismic_features.py`, con inflado cuadrático y en silencio.

Entrypoint para GitHub Actions:

    cd platform/backend && PYTHONPATH=. python -m scraper.sgc_sismos
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.session import AsyncSessionLocal
from infrastructure.external import sgc_client
from infrastructure.repositories.seismic_events import (
    assign_cluster,
    existing_source_row_ids,
    insert_events,
)
from scraper.common import httpx_client, log_scrape_run, utcnow

logger = logging.getLogger(__name__)

SOURCE_KEY = sgc_client.SOURCE_KEY

# Ventana de consulta por corrida. Con el job cada 15 min, 2 días dan un margen
# amplio: cubre un cron caído varias horas y las revisiones que el SGC publica
# tarde (un evento pasa de `automatic` a `manual` y cambia de magnitud).
LOOKBACK_DAYS = 2

# Solo los sismos que merecen un aviso en Slack. El feed trae decenas de eventos
# de M0.7-1.5 por semana; postearlos todos ahogaría el canal, que es justo lo que
# la regla anti-ruido de CLAUDE.md quiere evitar.
DIGEST_MIN_MAGNITUDE = 3.0


async def _collect() -> tuple[list[dict[str, Any]], str | None]:
    """Descarga y parsea. Devuelve (filas, detalle)."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    async with httpx_client() as client:
        rows = await sgc_client.fetch_events(client, start=start, end=end + timedelta(days=1))
    return rows, f"ventana={start}..{end} en_bbox={len(rows)}"


async def _run_sgc_sismos(session: AsyncSession) -> int:
    started = utcnow()
    status = "error"
    downloaded = 0
    inserted = 0
    discarded = 0
    detail: str | None = None
    new_items: list[dict[str, Any]] = []

    try:
        rows, detail = await _collect()
        downloaded = len(rows)

        # Una sola consulta para todo el lote, en vez de un SELECT por fila.
        known = await existing_source_row_ids(session, [r["source_row_id"] for r in rows])
        fresh = [r for r in rows if r["source_row_id"] not in known]
        discarded = downloaded - len(fresh)

        if fresh:
            inserted = await insert_events(session, fresh)

            # Agrupar en eventos canónicos DENTRO de la misma transacción, para
            # que no queden filas sin clúster si algo falla después.
            from sqlalchemy import select

            from db.models.seismic_event import SeismicEvent

            ids = [r["source_row_id"] for r in fresh]
            stmt = select(SeismicEvent).where(SeismicEvent.source_row_id.in_(ids))
            for ev in (await session.execute(stmt)).scalars().all():
                await assign_cluster(session, ev)

            for r in sorted(fresh, key=lambda x: x["magnitude"], reverse=True):
                if r["magnitude"] >= DIGEST_MIN_MAGNITUDE:
                    new_items.append(
                        {
                            "titulo": f"Sismo M{r['magnitude']} ({r['mag_type'] or 's/d'})",
                            "detalle": (
                                f"{r['epicenter_label'] or 'epicentro s/d'} · "
                                f"profundidad {r['depth_km']} km"
                            ),
                            "fecha": str(r["event_local_at"])[:19],
                        }
                    )

        await session.commit()
        status = "ok"
        logger.info("SGC sismos: %d nuevos de %d en la ventana", inserted, downloaded)
    except Exception as exc:  # noqa: BLE001
        detail = (detail + " | " if detail else "") + repr(exc)
        await session.rollback()
        raise
    finally:
        await log_scrape_run(
            session,
            source=SOURCE_KEY,
            status=status,
            run_started_at=started,
            records_downloaded=downloaded,
            records_valid=inserted,
            records_discarded=discarded,
            detail=detail,
            new_items_summary=new_items if status == "ok" else None,
        )
    return inserted


async def run_sgc_sismos_scraper(session: AsyncSession | None = None) -> int:
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_sgc_sismos(s)
    return await _run_sgc_sismos(session)


if __name__ == "__main__":
    from observability.logging_config import configure_logging

    configure_logging("scraper-sgc-sismos")
    asyncio.run(run_sgc_sismos_scraper())
