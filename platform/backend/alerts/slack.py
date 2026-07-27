from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.alert_scoring import compute_urgency_score, urgency_label
from domain.risk_rules import ANTECEDENT_INDEX_THRESHOLD_MM, compute_alert_state, normalize_category
from domain.validation import FAILURE_STATUSES, SUCCESS_STATUSES
from constants import (
    ALERT_COOLDOWN_CRITICAL_RISK_HOURS,
    ALERT_COOLDOWN_RAINFALL_HOURS,
    ALERT_COOLDOWN_SCRAPER_HOURS,
    ALERT_COOLDOWN_YELLOW_HOURS,
    SCRAPER_INTERVALS_MIN,
    SCRAPER_STALE_FACTOR,
)
from alerts.charts import ascii_sparkline, rainfall_chart_for_commune
from alerts.slack_media import (
    chart_url,
    dashboard_url,
    latest_explanation,
    recommendation_for,
    upload_chart_to_slack,
)
from db.models.alert_log import AlertLog
from db.models.app_setting import AppSetting
from db.models.scraping_log import ScrapingLog

logger = logging.getLogger(__name__)

COL_TZ = ZoneInfo("America/Bogota")

# Nombres desde la fuente única (domain/communes.py). Acepta id canónico
# ("18") Y código oficial ("60") porque hay datos históricos con ambos.
from domain.communes import COMMUNES as _COMMUNES

_NAMES: dict[str, str] = {c.id: c.nombre for c in _COMMUNES} | {
    c.official_code: c.nombre for c in _COMMUNES
}


def _midnight_utc() -> datetime:
    now_col = datetime.now(COL_TZ)
    return now_col.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


async def _get_webhook_url(session: AsyncSession) -> str | None:
    # Prioridad: configuración en BD (UI) → variable de entorno (deploy).
    row = await session.get(AppSetting, "slack_webhook_url")
    if row and row.value:
        return row.value
    return os.getenv("SLACK_WEBHOOK_URL") or None


async def _get_thresholds(session: AsyncSession) -> dict[str, float]:
    from infrastructure.repositories.rainfall import thresholds_by_commune

    return await thresholds_by_commune(session)


async def _get_today_acum(session: AsyncSession) -> dict[str, float]:
    from infrastructure.repositories.rainfall import accumulated_since_by_commune

    return await accumulated_since_by_commune(session, _midnight_utc())


async def _get_latest_risk(session: AsyncSession) -> dict[str, tuple[float | None, str | None]]:
    from infrastructure.repositories.risk_predictions import latest_scores_by_commune

    return await latest_scores_by_commune(session)


async def _was_recently_alerted(session: AsyncSession, commune_id: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ALERT_COOLDOWN_RAINFALL_HOURS)
    result = await session.execute(
        select(AlertLog)
        .where(AlertLog.commune_id == commune_id)
        .where(AlertLog.triggered_at >= cutoff)
        .where(AlertLog.status == "sent")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _fire_slack(webhook_url: str, payload: dict) -> tuple[str, int | None]:
    from infrastructure.external.slack_client import post_webhook

    return await post_webhook(webhook_url, payload)


def _urgency_context_element(score: int) -> dict:
    """Bloque `context` reusado por los 4 tipos de alerta para mostrar el
    score de urgencia (0-100) calculado en domain/alert_scoring.py."""
    return {
        "type": "mrkdwn",
        "text": f"⚡ Urgencia: {score}/100 ({urgency_label(score)})",
    }


def _dashboard_link_button() -> dict:
    """Botón de ENLACE (no interactivo — el backend no tiene URL pública
    accesible desde Slack, así que la interactividad real de Slack no es
    viable hoy). Reusado en los 4 tipos de alerta."""
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": "🗺️ Abrir dashboard"},
        "url": dashboard_url(),
        "style": "primary",
    }


async def _hours_since_appsetting(session: AsyncSession, key: str) -> float | None:
    """Horas desde el último ISO timestamp guardado en `app_settings[key]`,
    o None si nunca se guardó. Usado tanto para el chequeo de cooldown
    (booleano) como para alimentar el score de urgencia — misma fuente de
    datos, sin agregar tablas nuevas."""
    row = await session.get(AppSetting, key)
    if not row or not row.value:
        return None
    try:
        last_sent = datetime.fromisoformat(row.value)
    except ValueError:
        return None
    if last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last_sent).total_seconds() / 3600


async def _hours_since_last_rainfall_alert(session: AsyncSession, commune_id: str) -> float | None:
    result = await session.execute(
        select(AlertLog.triggered_at)
        .where(AlertLog.commune_id == commune_id)
        .where(AlertLog.status == "sent")
        .order_by(AlertLog.triggered_at.desc())
        .limit(1)
    )
    triggered_at = result.scalar_one_or_none()
    if triggered_at is None:
        return None
    if triggered_at.tzinfo is None:
        triggered_at = triggered_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - triggered_at).total_seconds() / 3600


def _build_slack_payload(
    commune_id: str,
    name: str,
    acum_mm: float,
    threshold_mm: float,
    risk_score: float | None,
    risk_category: str | None,
    urgency_score: int = 0,
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
                    {
                        "type": "mrkdwn",
                        "text": f"*Umbral configurado:*\n{threshold_mm:.1f} mm (+{excess_pct}%)",
                    },
                    {"type": "mrkdwn", "text": f"*Riesgo del modelo ML:*\n{risk_text}"},
                ],
            },
            {
                "type": "actions",
                "elements": [_dashboard_link_button()],
            },
            {
                "type": "context",
                "elements": [
                    _urgency_context_element(urgency_score),
                    {
                        "type": "mrkdwn",
                        "text": f"Hora Colombia: {datetime.now(COL_TZ).strftime('%Y-%m-%d %H:%M')} · Sistema TEYVA · Medellín",
                    },
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
        hours_since = await _hours_since_last_rainfall_alert(session, commune_id)
        urgency = compute_urgency_score(
            risk_category=risk_category, alert_type="rainfall", hours_since_last_alert=hours_since
        )
        payload = _build_slack_payload(
            commune_id,
            name,
            acum_mm,
            threshold_mm,
            risk_score,
            risk_category,
            urgency_score=urgency,
        )
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
            logger.info(
                "Slack alert sent for commune %s (%.1f mm > %.1f mm)",
                commune_id,
                acum_mm,
                threshold_mm,
            )

    await session.commit()
    return alerted


# ── Estado Amarillo (alistamiento) ────────────────────────────────────────────


async def _yellow_alert_on_cooldown(session: AsyncSession, commune_id: str) -> bool:
    key = f"yellow_alert_cooldown_{commune_id}"
    row = await session.get(AppSetting, key)
    if not row or not row.value:
        return False
    try:
        last_sent = datetime.fromisoformat(row.value)
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        return (
            datetime.now(timezone.utc) - last_sent
        ).total_seconds() < ALERT_COOLDOWN_YELLOW_HOURS * 3600
    except ValueError:
        return False


async def _mark_yellow_alert_sent(session: AsyncSession, commune_id: str) -> None:
    key = f"yellow_alert_cooldown_{commune_id}"
    row = await session.get(AppSetting, key)
    if row:
        row.value = datetime.now(timezone.utc).isoformat()
    else:
        session.add(AppSetting(key=key, value=datetime.now(timezone.utc).isoformat()))


def _build_yellow_alert_payload(
    commune_id: str, name: str, state: dict, urgency_score: int = 0
) -> dict:
    return {
        "attachments": [
            {
                "color": "#F2B705",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "🟡 Alistamiento — TEYVA"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Comuna:*\n{name} ({commune_id})"},
                            {
                                "type": "mrkdwn",
                                "text": f"*Lluvia hoy:*\n{state['rainfall_pct']:.0%} del umbral",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Índice antecedente:*\n{state['antecedent_pct']:.0%} de referencia",
                            },
                            {"type": "mrkdwn", "text": f"*Riesgo ML:*\n{state['risk_category']}"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"💡 *Acción:* {state['action']}"},
                    },
                    {
                        "type": "actions",
                        "elements": [_dashboard_link_button()],
                    },
                    {
                        "type": "context",
                        "elements": [
                            _urgency_context_element(urgency_score),
                            {
                                "type": "mrkdwn",
                                "text": f"Hora Colombia: {datetime.now(COL_TZ).strftime('%Y-%m-%d %H:%M')} · Sistema TEYVA",
                            },
                        ],
                    },
                ],
            }
        ]
    }


async def check_and_fire_yellow_alerts(session: AsyncSession) -> list[str]:
    """Alerta de alistamiento (estado AMARILLO) por comuna, vía
    `constants.compute_alert_state`. Distinto del riesgo crítico (ROJO), que
    ya dispara por `check_and_fire_critical_risk_alerts`. Cooldown propio por
    comuna para no duplicar avisos en cada corrida del scheduler."""
    from ml.precip_index import antecedent_indexes_for_all_communes

    webhook_url = await _get_webhook_url(session)
    if not webhook_url:
        return []

    thresholds = await _get_thresholds(session)
    acums = await _get_today_acum(session)
    risks = await _get_latest_risk(session)
    antecedent_by_commune = await antecedent_indexes_for_all_communes(session)

    alerted: list[str] = []
    for commune_id in set(acums) | set(antecedent_by_commune) | set(risks):
        threshold_mm = thresholds.get(commune_id, 35.0)
        rainfall_pct = round(acums.get(commune_id, 0.0) / threshold_mm, 3) if threshold_mm else 0.0
        antecedent_pct = round(
            antecedent_by_commune.get(commune_id, 0.0) / ANTECEDENT_INDEX_THRESHOLD_MM, 3
        )
        _, risk_category = risks.get(commune_id, (None, None))

        result = compute_alert_state(rainfall_pct, antecedent_pct, risk_category)
        if result["state"] != "AMARILLO":
            continue
        if await _yellow_alert_on_cooldown(session, commune_id):
            continue

        name = _NAMES.get(commune_id, f"Comuna {commune_id}")
        state_payload = {
            "rainfall_pct": rainfall_pct,
            "antecedent_pct": antecedent_pct,
            "risk_category": risk_category or "Sin datos",
            "action": result["action"],
        }
        hours_since = await _hours_since_appsetting(session, f"yellow_alert_cooldown_{commune_id}")
        urgency = compute_urgency_score(
            risk_category=risk_category, alert_type="yellow", hours_since_last_alert=hours_since
        )
        payload = _build_yellow_alert_payload(
            commune_id, name, state_payload, urgency_score=urgency
        )
        status, _ = await _fire_slack(webhook_url, payload)
        if status == "sent":
            await _mark_yellow_alert_sent(session, commune_id)
            alerted.append(commune_id)
            logger.info("Yellow alert sent for commune %s", commune_id)

    await session.commit()
    return alerted


# ── Scraper health alerts ─────────────────────────────────────────────────────

_SCRAPER_FAILURE_THRESHOLD = 3
_SCRAPER_INTERVALS: dict[str, int] = {
    "siata": 30,
    "dagrd": 60,
    "ideam": 360,
    "medellin_datos": 1440,
}
_SCRAPER_LABELS: dict[str, str] = {
    "siata": "SIATA (lluvia)",
    "dagrd": "DAGRD (eventos)",
    "ideam": "IDEAM (meteorología)",
    "medellin_datos": "Medellín Datos",
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
        return (
            datetime.now(timezone.utc) - last_sent
        ).total_seconds() < ALERT_COOLDOWN_SCRAPER_HOURS * 3600
    except ValueError:
        return False


async def _mark_scraper_alert_sent(session: AsyncSession, source: str) -> None:
    key = f"scraper_alert_cooldown_{source}"
    row = await session.get(AppSetting, key)
    if row:
        row.value = datetime.now(timezone.utc).isoformat()
    else:
        session.add(AppSetting(key=key, value=datetime.now(timezone.utc).isoformat()))


def _build_scraper_alert_payload(
    failing_sources: list[tuple[str, str]], urgency_score: int = 0
) -> dict:
    fields = []
    for source, reason in failing_sources:
        label = _SCRAPER_LABELS.get(source, source)
        fields.append({"type": "mrkdwn", "text": f"*{label}:*\n{reason}"})
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
                    "text": f"*{len(failing_sources)} fuente(s) de datos sin funcionar:*",
                },
            },
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [_dashboard_link_button()],
            },
            {
                "type": "context",
                "elements": [
                    _urgency_context_element(urgency_score),
                    {
                        "type": "mrkdwn",
                        "text": f"Hora Colombia: {datetime.now(COL_TZ).strftime('%Y-%m-%d %H:%M')} · Sistema TEYVA · Medellín",
                    },
                ],
            },
        ]
    }


def _humanize_minutes(minutes: int) -> str:
    if minutes < 120:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} días"


async def check_and_fire_scraper_alerts(session: AsyncSession) -> list[str]:
    """Alerta por Slack cuando una fuente está caída, por cualquiera de dos vías:

    1. Fallos consecutivos (>= _SCRAPER_FAILURE_THRESHOLD filas failed/error).
    2. Staleness: sin corrida exitosa hace más de SCRAPER_STALE_FACTOR × intervalo,
       incluyendo el caso de silencio total (cero filas — p. ej. GitHub Actions
       deshabilitado por inactividad, que fue exactamente lo que pasó sin que
       nadie se enterara). Los fallos consecutivos no cubren ese caso porque el
       silencio no deja filas de error.

    Devuelve las fuentes alertadas (respetando cooldown por fuente).
    """
    webhook_url = await _get_webhook_url(session)
    if not webhook_url:
        return []

    stmt = select(ScrapingLog).order_by(ScrapingLog.run_started_at.desc()).limit(200)
    result = await session.execute(stmt)
    all_rows = result.scalars().all()

    by_source: dict[str, list[ScrapingLog]] = {}
    for row in all_rows:
        if row.source not in by_source:
            by_source[row.source] = []
        by_source[row.source].append(row)

    now = datetime.now(timezone.utc)
    failing: list[tuple[str, str]] = []
    max_consecutive = 0

    # Vía 1: fallos consecutivos (fuentes que sí reportan, pero fallando).
    for source, rows in by_source.items():
        consecutive = 0
        for row in rows:
            if row.status in FAILURE_STATUSES:
                consecutive += 1
            elif row.status != "started":
                break
        if consecutive >= _SCRAPER_FAILURE_THRESHOLD:
            if not await _scraper_alert_on_cooldown(session, source):
                failing.append((source, f"{consecutive} fallos consecutivos"))
                max_consecutive = max(max_consecutive, consecutive)

    # Vía 2: staleness — se evalúa sobre TODAS las fuentes esperadas, no solo
    # las que tienen filas (una fuente que jamás corrió también debe alertar).
    already = {s for s, _ in failing}
    for source, interval_min in SCRAPER_INTERVALS_MIN.items():
        if source in already:
            continue
        rows = by_source.get(source, [])
        last_success_at: datetime | None = None
        for row in rows:
            if row.status in SUCCESS_STATUSES:
                ts = row.run_finished_at or row.run_started_at
                if ts is not None:
                    last_success_at = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
                break
        stale_limit = timedelta(minutes=interval_min * SCRAPER_STALE_FACTOR)
        if last_success_at is None:
            reason = "sin corridas exitosas registradas"
        elif now - last_success_at > stale_limit:
            lag_min = int((now - last_success_at).total_seconds() / 60)
            reason = f"sin datos nuevos hace {_humanize_minutes(lag_min)}"
        else:
            continue
        if not await _scraper_alert_on_cooldown(session, source):
            failing.append((source, reason))

    if not failing:
        return []

    # Urgencia agregada del lote: si CUALQUIER fuente del lote nunca se
    # alertó antes, el conjunto se trata como "hace rato no se avisa nada de
    # esto" (None); si todas ya se alertaron antes, se usa la más
    # desatendida (max) para no subestimar el peor caso del lote.
    hours_values: list[float] = []
    any_never_alerted = False
    for source, _ in failing:
        h = await _hours_since_appsetting(session, f"scraper_alert_cooldown_{source}")
        if h is None:
            any_never_alerted = True
        else:
            hours_values.append(h)
    hours_since_agg = None if any_never_alerted else (max(hours_values) if hours_values else None)
    urgency = compute_urgency_score(
        risk_category=None,
        alert_type="scraper",
        hours_since_last_alert=hours_since_agg,
        consecutive_failures=max_consecutive,
    )

    payload = _build_scraper_alert_payload(failing, urgency_score=urgency)
    status, _ = await _fire_slack(webhook_url, payload)

    alerted: list[str] = []
    if status == "sent":
        for source, _ in failing:
            await _mark_scraper_alert_sent(session, source)
            alerted.append(source)
        logger.info("Scraper health alert sent for: %s", alerted)

    await session.commit()
    return alerted


# ── Critical risk alerts ──────────────────────────────────────────────────────


async def _critical_risk_alert_on_cooldown(session: AsyncSession, commune_id: str) -> bool:
    key = f"critical_risk_alert_{commune_id}"
    row = await session.get(AppSetting, key)
    if not row or not row.value:
        return False
    try:
        last_sent = datetime.fromisoformat(row.value)
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        return (
            datetime.now(timezone.utc) - last_sent
        ).total_seconds() < ALERT_COOLDOWN_CRITICAL_RISK_HOURS * 3600
    except ValueError:
        return False


async def _mark_critical_risk_alert_sent(session: AsyncSession, commune_id: str) -> None:
    key = f"critical_risk_alert_{commune_id}"
    row = await session.get(AppSetting, key)
    if row:
        row.value = datetime.now(timezone.utc).isoformat()
    else:
        session.add(AppSetting(key=key, value=datetime.now(timezone.utc).isoformat()))


def _build_critical_risk_payload(
    commune_id: str,
    name: str,
    risk_score: float,
    risk_category: str,
    explanation: str | None,
    recommendation: str,
    sparkline: str,
    daily_values: list[float],
    explanation_structured: dict | None = None,
    urgency_score: int = 0,
) -> dict:
    """Mensaje enriquecido de webhook: datos + por qué + recomendación + links."""
    rain_summary = (
        f"`{sparkline}`  (máx {max(daily_values):.0f} mm)"
        if daily_values
        else "Sin datos de lluvia"
    )
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔴 RIESGO CRÍTICO — TEYVA"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Comuna:*\n{name} ({commune_id})"},
                {"type": "mrkdwn", "text": f"*Nivel de riesgo:*\n{risk_category.upper()}"},
                {"type": "mrkdwn", "text": f"*Probabilidad:*\n{risk_score:.1%}"},
                {"type": "mrkdwn", "text": f"*Lluvia 7d:*\n{rain_summary}"},
            ],
        },
    ]
    factors = explanation_structured.get("factors") if explanation_structured else None
    if factors and isinstance(factors, list):
        # Estructura disponible → viñetas Slack-nativas, legibles de un vistazo.
        factors_md = "\n".join(f"• {f}" for f in factors)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📊 *Por qué:*\n{factors_md}"},
            }
        )
    elif explanation:
        # Fallback a texto plano si no hay estructura (filas legacy sin explanation_json).
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📊 *Por qué:* {explanation}"},
            }
        )
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"💡 *Recomendación:* {recommendation}"},
        }
    )
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📈 Ver gráfica"},
                    "url": chart_url(commune_id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🗺️ Abrir dashboard"},
                    "url": dashboard_url(),
                    "style": "primary",
                },
            ],
        }
    )
    blocks.append(
        {
            "type": "context",
            "elements": [
                _urgency_context_element(urgency_score),
                {
                    "type": "mrkdwn",
                    "text": f"☎️ DAGRD 4444444 · Bomberos 119 · Cruz Roja 132 · {datetime.now(COL_TZ).strftime('%Y-%m-%d %H:%M')} Colombia",
                },
            ],
        }
    )
    return {"blocks": blocks}


async def check_and_fire_critical_risk_alerts(session: AsyncSession) -> list[str]:
    """Fire Slack alert if any commune hits CRÍTICO risk. Returns alerted commune IDs (with cooldown)."""
    webhook_url = await _get_webhook_url(session)
    if not webhook_url:
        return []

    # Get latest predictions for all communes
    from infrastructure.repositories.risk_predictions import latest_by_commune

    predictions = (await latest_by_commune(session)).values()

    critical_communes: list[tuple[str, float]] = []
    for pred in predictions:
        # Normalize category: "critico", "Crítico", "CRITICO" all become "critico"
        if normalize_category(pred.risk_category) == "critico":
            if not await _critical_risk_alert_on_cooldown(session, pred.commune_id):
                critical_communes.append((pred.commune_id, pred.risk_score))

    if not critical_communes:
        return []

    # Umbrales por comuna (para la línea de la gráfica)
    thresholds = await _get_thresholds(session)

    alerted: list[str] = []
    for commune_id, risk_score in critical_communes:
        name = _NAMES.get(commune_id, f"Comuna {commune_id}")
        threshold_mm = thresholds.get(commune_id, 35.0)
        explanation_row = await latest_explanation(session, commune_id)
        explanation, explanation_structured = explanation_row if explanation_row else (None, None)
        factors = explanation_structured.get("factors") if explanation_structured else None
        recommendation = recommendation_for("critico")

        # Generar gráfica de lluvia (el "por qué" visual)
        try:
            png, daily_values = await rainfall_chart_for_commune(
                commune_id, session, threshold_mm, name, "critico", risk_score
            )
        except Exception as exc:
            logger.warning("No se pudo generar gráfica para comuna %s: %s", commune_id, exc)
            png, daily_values = None, []

        sparkline = ascii_sparkline(daily_values)
        sent_ok = False

        hours_since = await _hours_since_appsetting(session, f"critical_risk_alert_{commune_id}")
        urgency = compute_urgency_score(
            risk_category="critico", alert_type="critical_risk", hours_since_last_alert=hours_since
        )

        # "Por qué": viñetas si hay factores estructurados, texto plano si no.
        if factors and isinstance(factors, list):
            why_line = "📊 *Por qué:*\n" + "\n".join(f"• {f}" for f in factors) + "\n"
        elif explanation:
            why_line = f"📊 *Por qué:* {explanation}\n"
        else:
            why_line = ""

        # 1) Intentar imagen inline vía bot token (forma profesional)
        if png is not None:
            comment = (
                f"🔴 *RIESGO CRÍTICO — {name} ({commune_id})*  ·  Probabilidad {risk_score:.0%}\n"
                + why_line
                + f"💡 *Recomendación:* {recommendation}\n"
                f"⚡ Urgencia: {urgency}/100 ({urgency_label(urgency)})\n"
                f"🗺️ {dashboard_url()}  ·  ☎️ DAGRD 4444444"
            )
            sent_ok = await upload_chart_to_slack(
                png,
                f"riesgo_critico_comuna_{commune_id}.png",
                f"Riesgo crítico — {name}",
                comment,
            )

        # 2) Fallback: webhook enriquecido (texto + sparkline + links)
        if not sent_ok:
            payload = _build_critical_risk_payload(
                commune_id,
                name,
                risk_score,
                "crítico",
                explanation,
                recommendation,
                sparkline,
                daily_values,
                explanation_structured=explanation_structured,
                urgency_score=urgency,
            )
            status, _ = await _fire_slack(webhook_url, payload)
            sent_ok = status == "sent"

        if sent_ok:
            await _mark_critical_risk_alert_sent(session, commune_id)
            alerted.append(commune_id)
            logger.critical(
                "CRITICAL RISK alert sent for commune %s (risk_score=%.3f)", commune_id, risk_score
            )

    await session.commit()
    return alerted
