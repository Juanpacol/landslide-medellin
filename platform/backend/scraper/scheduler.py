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
    """Watches the sources' health and alerts via Slack if any is down.

    Covers both consecutive failures and total silence (a source that
    stopped reporting — e.g. GitHub Actions disabled). A silent no-op
    without SLACK_WEBHOOK_URL configured.
    """
    from application.fire_alerts import alerts_scraper_watchdog
    from db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            alerted = await alerts_scraper_watchdog(session)
            if alerted:
                logger.warning("Watchdog: Slack alerts sent for %s", alerted)
    except Exception:
        logger.exception("Scraper watchdog failed")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # next_run_time close to "now": without this, an interval-N job waits a
    # full N before its first firing. In environments that restart often
    # (local Docker, laptops), the 6h/24h sources never got to run. Staggered
    # by a few seconds so they don't hit the DB/network all at once.
    now = datetime.now(timezone.utc)
    scheduler.add_job(
        run_siata_scraper,
        "interval",
        minutes=30,
        id="siata_pluvio",
        replace_existing=True,
        next_run_time=now + timedelta(seconds=5),
    )
    scheduler.add_job(
        run_dagrd_scraper,
        "interval",
        hours=1,
        id="dagrd_wp",
        replace_existing=True,
        next_run_time=now + timedelta(seconds=20),
    )
    scheduler.add_job(
        run_ideam_scraper,
        "interval",
        hours=6,
        id="ideam_socrata",
        replace_existing=True,
        next_run_time=now + timedelta(seconds=35),
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
        run_siata_sismos_scraper,
        "interval",
        minutes=30,
        id="siata_sismos",
        replace_existing=True,
        next_run_time=now + timedelta(seconds=65),
    )
    # Watchdog: alerts via Slack if any source has gone too long without data.
    # Starts at 5 min (gives the initial scrapers time to populate logs).
    scheduler.add_job(
        run_scraper_watchdog,
        "interval",
        minutes=30,
        id="scraper_watchdog",
        replace_existing=True,
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
