"""Agente: valida integridad de datos tras cada ingesta de scraper.

Corre automáticamente después de `scraper/siata.py`, `scraper/dagrd.py`, etc.
Detecta:
- Rangos inválidos (lluvia >500mm, sismos >10 magnitud, etc.)
- Timestamps inválidos (futuro)
- Cobertura: comunas sin datos de lluvia en tiempo reciente

Resultado → agent_run_logs (siempre) + alerta Slack si warning/critical.
Nunca bloquea la corrida del scraper.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.rainfall_timeseries import RainfallTimeseries
from db.models.seismic_event import SeismicEvent
from db.session import AsyncSessionLocal
from domain.communes import COMMUNES
from monitoring.notify import fire_agent_alert

logger = logging.getLogger(__name__)

# Umbrales de validación (mover a constants.py si empiezan a variar)
MIN_PRECIP_MM = 0.0
MAX_PRECIP_MM = 500.0
MIN_SEISMIC_MAG = 0.0
MAX_SEISMIC_MAG = 10.0


async def validate_rainfall_data(session: AsyncSession) -> tuple[str, dict]:
    """Valida registros recientes de lluvia (rainfall_timeseries)."""
    stmt = (
        select(RainfallTimeseries)
        .order_by(RainfallTimeseries.snapshot_at.desc())
        .limit(1000)
    )
    rows = (await session.scalars(stmt)).all()

    now = datetime.now(timezone.utc)
    out_of_range = 0
    future_timestamps = 0
    for row in rows:
        if not (MIN_PRECIP_MM <= row.precip_mm <= MAX_PRECIP_MM):
            out_of_range += 1
            logger.warning(
                "Rainfall out of range: %.1fmm commune=%s at %s",
                row.precip_mm, row.commune_id, row.snapshot_at,
            )
        if row.snapshot_at and row.snapshot_at > now:
            future_timestamps += 1

    findings = {
        "rainfall_checks": {
            "total_checked": len(rows),
            "out_of_range": out_of_range,
            "future_timestamps": future_timestamps,
            "range": f"{MIN_PRECIP_MM}-{MAX_PRECIP_MM}mm",
        }
    }
    status = "warning" if (out_of_range or future_timestamps) else "ok"
    return status, findings


async def validate_seismic_data(session: AsyncSession) -> tuple[str, dict]:
    """Valida registros sísmicos recientes."""
    stmt = select(SeismicEvent).order_by(SeismicEvent.ingested_at.desc()).limit(500)
    rows = (await session.scalars(stmt)).all()

    out_of_range = 0
    for row in rows:
        if row.magnitude is not None and not (MIN_SEISMIC_MAG <= row.magnitude <= MAX_SEISMIC_MAG):
            out_of_range += 1
            logger.warning(
                "Seismic event out of range: magnitude=%s at %s", row.magnitude, row.event_local_at,
            )

    findings = {
        "seismic_checks": {
            "total_checked": len(rows),
            "out_of_range": out_of_range,
            "range": f"{MIN_SEISMIC_MAG}-{MAX_SEISMIC_MAG}",
        }
    }
    status = "warning" if out_of_range else "ok"
    return status, findings


async def validate_geo_coverage(session: AsyncSession) -> tuple[str, dict]:
    """Detecta comunas sin datos de lluvia en las últimas 24h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    stmt = select(RainfallTimeseries.commune_id).where(
        RainfallTimeseries.snapshot_at >= cutoff
    )
    covered = {row[0] for row in (await session.execute(stmt)).all()}

    all_communes = {c.id for c in COMMUNES}
    missing = sorted(all_communes - covered)

    findings = {
        "coverage_checks": {
            "covered_communes": len(covered),
            "total_communes": len(all_communes),
            "missing_communes": missing,
        }
    }
    status = "warning" if missing else "ok"
    return status, findings


def _worse(a: str, b: str) -> str:
    order = {"ok": 0, "warning": 1, "critical": 2, "error": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


async def run() -> None:
    """Ejecuta todas las validaciones y reporta a Slack."""
    try:
        async with AsyncSessionLocal() as session:
            all_findings: dict = {}
            worst_status = "ok"

            for check in (validate_rainfall_data, validate_seismic_data, validate_geo_coverage):
                status, findings = await check(session)
                all_findings.update(findings)
                worst_status = _worse(worst_status, status)

            await fire_agent_alert(
                session,
                agent_name="scraper-data-validator",
                status=worst_status,
                summary=f"Scraper data validation: {worst_status.upper()}",
                detail=all_findings if worst_status != "ok" else None,
            )
    except Exception as e:
        logger.exception("Scraper validator failed")
        try:
            async with AsyncSessionLocal() as session:
                await fire_agent_alert(
                    session,
                    agent_name="scraper-data-validator",
                    status="error",
                    summary=f"Scraper validator error: {e}",
                )
        except Exception:
            logger.exception("Failed to report validator error")


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
