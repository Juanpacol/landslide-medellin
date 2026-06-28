from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.alert_log import AlertLog
from db.models.app_setting import AppSetting
from db.models.commune_threshold import CommuneThreshold
from db.models.rainfall_timeseries import RainfallTimeseries
from db.models.risk_prediction import RiskPrediction
from db.models.scraping_log import ScrapingLog

logger = logging.getLogger(__name__)

COL_TZ = ZoneInfo("America/Bogota")
COOLDOWN_HOURS = 6

_NAMES: dict[str, str] = {
    "1": "Popular", "2": "Santa Cruz", "3": "Manrique", "4": "Aranjuez",
    "5": "Castilla", "6": "Doce de Octubre", "7": "Robledo", "8": "Villa Hermosa",
    "9": "Buenos Aires", "10": "La Candelaria", "11": "Laureles-Estadio",
    "12": "La América", "13": "San Javier", "14": "El Poblado", "15": "Guayabal",
    "16": "Belén", "50": "Palmitas", "60": "San Cristóbal", "70": "Altavista",
    "80": "San Antonio de Prado", "90": "Santa Elena",
}


def _midnight_utc() -> datetime:
    now_col = datetime.now(COL_TZ)
    return now_col.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


async def _get_webhook_url(session: AsyncSession) -> str | None:
    row = await session.get(AppSetting, "slack_webhook_url")
    return row.value if row else None


async def _get_thresholds(session: AsyncSession) -> dict[str, float]:
    result = await session.execute(select(CommuneThreshold))
    return {r.commune_id: r.threshold_mm for r in result.scalars().all()}


async def _get_today_acum(session: AsyncSession) -> dict[str, float]:
    midnight = _midnight_utc()
    result = await session.execute(
        select(RainfallTimeseries.commune_id, func.sum(RainfallTimeseries.precip_mm))
        .where(RainfallTimeseries.snapshot_at >= midnight)
        .group_by(RainfallTimeseries.commune_id)
    )
    return {row[0]: float(row[1]) for row in result.all()}


async def _get_latest_risk(session: AsyncSession) -> dict[str, tuple[float | None, str | None]]:
    subq = (
        select(RiskPrediction.commune_id, func.max(RiskPrediction.created_at).label("max_at"))
        .group_by(RiskPrediction.commune_id)
        .subquery()
    )
    result = await session.execute(
        select(RiskPrediction).join(
            subq,
            (RiskPrediction.commune_id == subq.c.commune_id)
            & (RiskPrediction.created_at == subq.c.max_at),
        )
    )
    return {r.commune_id: (r.risk_score, r.risk_category) for r in result.scalars().all()}


async def _was_recently_alerted(session: AsyncSession, commune_id: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=COOLDOWN_HOURS)
    result = await session.execute(
        select(AlertLog)
        .where(AlertLog.commune_id == commune_id)
        .where(AlertLog.triggered_at >= cutoff)
        .where(AlertLog.status == "sent")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _fire_slack(webhook_url: str, payload: dict) -> tuple[str, int | None]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(webhook_url, json=payload)
            return ("sent" if r.status_code == 200 else "failed"), r.status_code
    except Exception as exc:
        logger.warning("Slack webhook error: %s", exc)
        return "failed", None


def _build_slack_payload(
    commune_id: str,
    name: str,
    acum_mm: float,
    threshold_mm: float,
    risk_score: float | None,
    risk_category: str | None,
) -> dict:
    excess_pct = round((acum_mm - threshold_mm) / threshold_mm * 100)
    risk_text = f"{risk_category} ({risk_score:.2f})" if risk_score is not None else "Sin datos"
    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Alerta de Lluvia — TEYVA"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Comuna:*\n{name} ({commune_id})"},
                    {"type": "mrkdwn", "text": f"*Lluvia acumulada hoy:*\n{acum_mm:.1f} mm"},
                    {"type": "mrkdwn", "text": f"*Umbral configurado:*\n{threshold_mm:.1f} mm (+{excess_pct}%)"},
                    {"type": "mrkdwn", "text": f"*Riesgo del modelo ML:*\n{risk_text}"},
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Hora Colombia: {datetime.now(COL_TZ).strftime('%Y-%m-%d %H:%M')} · Sistema TEYVA · Medellín",
                    }
                ],
            },
        ]
    }


async def check_and_fire_alerts(session: AsyncSession) -> list[str]:
    """Check rainfall thresholds and fire Slack webhooks. Returns alerted commune IDs."""
    webhook_url = await _get_webhook_url(session)
    if not webhook_url:
        return []

    thresholds = await _get_thresholds(session)
    acums = await _get_today_acum(session)
    risks = await _get_latest_risk(session)

    now_utc = datetime.now(timezone.utc)
    alerted: list[str] = []

    for commune_id, acum_mm in acums.items():
        threshold_mm = thresholds.get(commune_id, 35.0)
        if acum_mm <= threshold_mm:
            continue

        if await _was_recently_alerted(session, commune_id):
            session.add(
                AlertLog(
                    commune_id=commune_id,
                    triggered_at=now_utc,
                    precip_acum_mm=acum_mm,
                    threshold_mm=threshold_mm,
                    webhook_url=webhook_url,
                    status="cooldown",
                )
            )
            continue

        name = _NAMES.get(commune_id, f"Comuna {commune_id}")
        risk_score, risk_category = risks.get(commune_id, (None, None))
        payload = _build_slack_payload(commune_id, name, acum_mm, threshold_mm, risk_score, risk_category)
        status, code = await _fire_slack(webhook_url, payload)

        session.add(
            AlertLog(
                commune_id=commune_id,
                triggered_at=now_utc,
                precip_acum_mm=acum_mm,
                threshold_mm=threshold_mm,
                risk_score=risk_score,
                risk_category=risk_category,
                webhook_url=webhook_url,
                status=status,
                response_code=code,
            )
        )
        if status == "sent":
            alerted.append(commune_id)
            logger.info("Slack alert sent for commune %s (%.1f mm > %.1f mm)", commune_id, acum_mm, threshold_mm)

    await session.commit()
    return alerted


# ── Scraper health alerts ─────────────────────────────────────────────────────

_SCRAPER_FAILURE_THRESHOLD = 3
_SCRAPER_INTERVALS: dict[str, int] = {
    "siata": 30, "dagrd": 60, "ideam": 360, "medellin_datos": 1440,
}
_SCRAPER_LABELS: dict[str, str] = {
    "siata": "SIATA (lluvia)", "dagrd": "DAGRD (eventos)",
    "ideam": "IDEAM (meteorología)", "medellin_datos": "Medellín Datos",
}


async def _scraper_alert_on_cooldown(session: AsyncSession, source: str) -> bool:
    key = f"scraper_alert_cooldown_{source}"
    row = await session.get(AppSetting, key)
    if not row or not row.value:
        return False
    try:
        last_sent = datetime.fromisoformat(row.value)
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_sent).total_seconds() < COOLDOWN_HOURS * 3600
    except ValueError:
        return False


async def _mark_scraper_alert_sent(session: AsyncSession, source: str) -> None:
    key = f"scraper_alert_cooldown_{source}"
    row = await session.get(AppSetting, key)
    if row:
        row.value = datetime.now(timezone.utc).isoformat()
    else:
        session.add(AppSetting(key=key, value=datetime.now(timezone.utc).isoformat()))


def _build_scraper_alert_payload(failing_sources: list[tuple[str, int]]) -> dict:
    fields = []
    for source, failures in failing_sources:
        label = _SCRAPER_LABELS.get(source, source)
        fields.append({"type": "mrkdwn", "text": f"*{label}:*\n{failures} fallos consecutivos"})
    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "⚠️ Scraper caído — TEYVA"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{len(failing_sources)} fuente(s) con {_SCRAPER_FAILURE_THRESHOLD}+ fallos seguidos:*",
                },
            },
            {"type": "section", "fields": fields},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Hora Colombia: {datetime.now(COL_TZ).strftime('%Y-%m-%d %H:%M')} · Sistema TEYVA · Medellín",
                    }
                ],
            },
        ]
    }


async def check_and_fire_scraper_alerts(session: AsyncSession) -> list[str]:
    """Fire Slack alert if any scraper source has >= 3 consecutive failures. Returns alerted sources."""
    webhook_url = await _get_webhook_url(session)
    if not webhook_url:
        return []

    stmt = (
        select(ScrapingLog)
        .order_by(ScrapingLog.run_started_at.desc())
        .limit(200)
    )
    result = await session.execute(stmt)
    all_rows = result.scalars().all()

    by_source: dict[str, list[ScrapingLog]] = {}
    for row in all_rows:
        if row.source not in by_source:
            by_source[row.source] = []
        by_source[row.source].append(row)

    failing: list[tuple[str, int]] = []
    for source, rows in by_source.items():
        consecutive = 0
        for row in rows:
            if row.status in ("failed", "error"):
                consecutive += 1
            elif row.status != "started":
                break
        if consecutive >= _SCRAPER_FAILURE_THRESHOLD:
            if not await _scraper_alert_on_cooldown(session, source):
                failing.append((source, consecutive))

    if not failing:
        return []

    payload = _build_scraper_alert_payload(failing)
    status, _ = await _fire_slack(webhook_url, payload)

    alerted: list[str] = []
    if status == "sent":
        for source, _ in failing:
            await _mark_scraper_alert_sent(session, source)
            alerted.append(source)
        logger.info("Scraper health alert sent for: %s", alerted)

    await session.commit()
    return alerted
