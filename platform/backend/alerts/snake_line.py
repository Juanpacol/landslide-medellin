"""
Snake Line — gráfico de decisión 2D (metodología JMA).

En vez de un umbral de una sola variable ("lluvia > 30mm = alerta"), cruza
dos ejes:

    Eje X: Soil Water Index (% de saturación del suelo, `ml/soil_water_index.py`)
    Eje Y: lluvia de los últimos 60 minutos (mm)

Y compara el punto actual contra una "línea crítica" precalculada. La curva
que dibuja el punto en el tiempo es la "serpiente": si cruza la línea, el
suelo está en condición de falla (saturado + aguacero), no solo lloviendo.

Reduce falsos positivos frente a un umbral de una sola variable: un aguacero
de 80mm sobre suelo seco (SWI bajo) drena rápido y no cruza la línea; un
aguacero de 20mm sobre suelo ya saturado (SWI alto) sí la cruza.

MVP explícito: la línea crítica (`CRITICAL_LINES`) es la misma para todas las
comunas por ahora — no hay series históricas de deslizamientos con timestamp
preciso para calibrar una línea por comuna todavía. Los parámetros son
conservadores, de literatura JMA adaptada, no ajustados a Medellín.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.rainfall_timeseries import RainfallTimeseries
from ml.soil_water_index import compute_swi

logger = logging.getLogger(__name__)

HISTORY_HOURS = 48
TRAILING_RAIN_MINUTES = 60
SNAKE_LINE_COOLDOWN_HOURS = 2

# y = slope * x + intercept. Con soil saturado (x=100) casi cualquier lluvia
# es crítica (y≈0); con suelo seco (x=0) hace falta un aguacero fuerte (y≈50mm/h).
CRITICAL_LINES: dict[str, dict[str, float]] = {
    "default": {"slope": -0.5, "intercept": 50.0},
}


def _critical_y(x_swi: float, commune_id: str) -> float:
    line = CRITICAL_LINES.get(commune_id, CRITICAL_LINES["default"])
    return line["slope"] * x_swi + line["intercept"]


def classify_point(x_swi: float, y_rain_60min: float, commune_id: str) -> str:
    """Classifies a (SWI, trailing rain) point against the commune's critical line."""
    critical_y = _critical_y(x_swi, commune_id)
    if y_rain_60min >= critical_y:
        return "ROJO"
    if y_rain_60min >= critical_y * 0.8:
        return "AMARILLO"
    return "VERDE"


async def _daily_rain_for_commune(
    session: AsyncSession, commune_id: str, start: datetime, end: datetime
) -> dict[date, float]:
    from sqlalchemy import func

    stmt = (
        select(func.date(RainfallTimeseries.snapshot_at), func.sum(RainfallTimeseries.precip_mm))
        .where(
            RainfallTimeseries.commune_id == commune_id,
            RainfallTimeseries.snapshot_at >= start,
            RainfallTimeseries.snapshot_at <= end,
        )
        .group_by(func.date(RainfallTimeseries.snapshot_at))
    )
    out: dict[date, float] = {}
    for day_value, total in (await session.execute(stmt)).all():
        d = (
            day_value
            if isinstance(day_value, date)
            else datetime.fromisoformat(str(day_value)).date()
        )
        out[d] = float(total or 0.0)
    return out


async def get_snake_line_status(
    session: AsyncSession, commune_id: str, now: datetime | None = None
) -> dict:
    """Punto actual (x=SWI%, y=lluvia últimos 60min) + historial de 48h."""
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(hours=HISTORY_HOURS)
    swi_lookback_start = window_start - timedelta(days=30)

    daily_rain = await _daily_rain_for_commune(session, commune_id, swi_lookback_start, now)

    raw_stmt = (
        select(RainfallTimeseries.snapshot_at, RainfallTimeseries.precip_mm)
        .where(
            RainfallTimeseries.commune_id == commune_id,
            RainfallTimeseries.snapshot_at
            >= window_start - timedelta(minutes=TRAILING_RAIN_MINUTES),
        )
        .order_by(RainfallTimeseries.snapshot_at)
    )
    raw_rows = [(ts, float(p or 0.0)) for ts, p in (await session.execute(raw_stmt)).all()]

    def trailing_rain(at: datetime) -> float:
        trailing_start = at - timedelta(minutes=TRAILING_RAIN_MINUTES)
        return round(sum(p for ts, p in raw_rows if trailing_start < ts <= at), 2)

    swi_cache: dict[date, float] = {}

    def swi_for_day(d: date) -> float:
        if d not in swi_cache:
            swi_cache[d] = compute_swi(daily_rain, d)
        return swi_cache[d]

    history = []
    for ts, _ in raw_rows:
        if ts < window_start:
            continue
        x = swi_for_day(ts.date())
        y = trailing_rain(ts)
        history.append(
            {
                "timestamp": ts.isoformat(),
                "x": x,
                "y": y,
                "status": classify_point(x, y, commune_id),
            }
        )

    current_x = swi_for_day(now.date())
    current_y = trailing_rain(now)
    current_status = classify_point(current_x, current_y, commune_id)

    return {
        "commune_id": commune_id,
        "x": current_x,
        "y": current_y,
        "status": current_status,
        "critical_line": CRITICAL_LINES.get(commune_id, CRITICAL_LINES["default"]),
        "timestamp": now.isoformat(),
        "history": history,
    }


async def _snake_alert_on_cooldown(session: AsyncSession, commune_id: str) -> bool:
    from db.models.app_setting import AppSetting

    key = f"snake_line_alert_cooldown_{commune_id}"
    row = await session.get(AppSetting, key)
    if not row or not row.value:
        return False
    try:
        last_sent = datetime.fromisoformat(row.value)
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        return (
            datetime.now(timezone.utc) - last_sent
        ).total_seconds() < SNAKE_LINE_COOLDOWN_HOURS * 3600
    except ValueError:
        return False


async def _mark_snake_alert_sent(session: AsyncSession, commune_id: str) -> None:
    from db.models.app_setting import AppSetting

    key = f"snake_line_alert_cooldown_{commune_id}"
    row = await session.get(AppSetting, key)
    if row:
        row.value = datetime.now(timezone.utc).isoformat()
    else:
        session.add(AppSetting(key=key, value=datetime.now(timezone.utc).isoformat()))


def _build_snake_line_payload(commune_id: str, name: str, point: dict) -> dict:
    return {
        "attachments": [
            {
                "color": "#D93025",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "🐍 Snake Line — Línea crítica cruzada",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Comuna:*\n{name} ({commune_id})"},
                            {"type": "mrkdwn", "text": f"*Saturación (SWI):*\n{point['x']:.0f}%"},
                            {
                                "type": "mrkdwn",
                                "text": f"*Lluvia últimos 60min:*\n{point['y']:.1f} mm",
                            },
                        ],
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "⚠️ Combinación de suelo saturado + lluvia intensa — condición de falla según metodología JMA. Verificar en terreno.",
                        },
                    },
                ],
            }
        ]
    }


async def check_and_fire_snake_line_alerts(
    session: AsyncSession, commune_ids: list[str]
) -> list[str]:
    """Dispara Slack cuando el punto actual (SWI × lluvia 60min) de una comuna
    cruza la línea crítica (estado ROJO). Cooldown propio por comuna."""
    from alerts.slack import _NAMES, _fire_slack, _get_webhook_url

    webhook_url = await _get_webhook_url(session)
    if not webhook_url:
        return []

    alerted: list[str] = []
    for commune_id in commune_ids:
        try:
            point = await get_snake_line_status(session, commune_id)
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo calcular Snake Line para comuna %s", commune_id)
            continue

        if point["status"] != "ROJO":
            continue
        if await _snake_alert_on_cooldown(session, commune_id):
            continue

        name = _NAMES.get(commune_id, f"Comuna {commune_id}")
        payload = _build_snake_line_payload(commune_id, name, point)
        status, _ = await _fire_slack(webhook_url, payload)
        if status == "sent":
            await _mark_snake_alert_sent(session, commune_id)
            alerted.append(commune_id)
            logger.info("Snake Line alert sent for commune %s", commune_id)

    await session.commit()
    return alerted
