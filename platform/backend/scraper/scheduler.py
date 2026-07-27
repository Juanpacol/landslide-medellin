from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from scraper.dagrd import run_dagrd_scraper
from scraper.ideam import run_ideam_scraper
from scraper.medellin_datos import run_medellin_datos_scraper
from scraper.siata import run_siata_scraper
from scraper.siata_sismos import run_siata_sismos_scraper

logger = logging.getLogger(__name__)


async def run_scraper_watchdog() -> None:
    """Vigila la salud de las fuentes y alerta por Slack si alguna está caída.

    Cubre tanto fallos consecutivos como silencio total (fuente que dejó de
    reportar — p. ej. GitHub Actions deshabilitado). Sin SLACK_WEBHOOK_URL
    configurado es un no-op silencioso.
    """
    from application.fire_alerts import alerts_scraper_watchdog
    from db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            alerted = await alerts_scraper_watchdog(session)
            if alerted:
                logger.warning("Watchdog: alertas Slack enviadas para %s", alerted)
    except Exception:
        logger.exception("Watchdog de scrapers falló")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # next_run_time cercano a "ahora": sin esto, un job de intervalo N espera N
    # completo antes del primer disparo. En entornos que se reinician seguido
    # (Docker local, laptops) las fuentes de 6h/24h no llegaban a correr nunca.
    # Se escalonan unos segundos para no golpear la BD/red al mismo tiempo.
    now = datetime.now(timezone.utc)
    scheduler.add_job(
        run_siata_scraper, "interval", minutes=30,
        id="siata_pluvio", replace_existing=True, next_run_time=now + timedelta(seconds=5),
    )
    scheduler.add_job(
        run_dagrd_scraper, "interval", hours=1,
        id="dagrd_wp", replace_existing=True, next_run_time=now + timedelta(seconds=20),
    )
    scheduler.add_job(
        run_ideam_scraper, "interval", hours=6,
        id="ideam_socrata", replace_existing=True, next_run_time=now + timedelta(seconds=35),
    )
    scheduler.add_job(
        run_medellin_datos_scraper,
        "interval",
        hours=24,
        id="medellin_datos_arcgis",
        replace_existing=True,
        next_run_time=now + timedelta(seconds=50),
    )
    scheduler.add_job(
        run_siata_sismos_scraper, "interval", minutes=30,
        id="siata_sismos", replace_existing=True, next_run_time=now + timedelta(seconds=65),
    )
    # Watchdog: alerta por Slack si alguna fuente lleva demasiado sin datos.
    # Arranca a los 5 min (les da tiempo a los scrapers iniciales de poblar logs).
    scheduler.add_job(
        run_scraper_watchdog, "interval", minutes=30,
        id="scraper_watchdog", replace_existing=True,
        next_run_time=now + timedelta(minutes=5),
    )
    return scheduler


async def main() -> None:
    from observability.logging_config import configure_logging

    configure_logging("scraper-scheduler")
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("TEYVA scraper scheduler started (Ctrl+C to stop).")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
