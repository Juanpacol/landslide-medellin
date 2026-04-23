from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from scraper.dagrd import run_dagrd_scraper
from scraper.ideam import run_ideam_scraper
from scraper.medellin_datos import run_medellin_datos_scraper
from scraper.siata import run_siata_scraper

logger = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(run_siata_scraper, "interval", minutes=30, id="siata_pluvio", replace_existing=True)
    scheduler.add_job(run_dagrd_scraper, "interval", hours=1, id="dagrd_wp", replace_existing=True)
    scheduler.add_job(run_ideam_scraper, "interval", hours=6, id="ideam_socrata", replace_existing=True)
    scheduler.add_job(
        run_medellin_datos_scraper,
        "interval",
        hours=24,
        id="medellin_datos_arcgis",
        replace_existing=True,
    )
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("TEYVA scraper scheduler started (Ctrl+C to stop).")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
