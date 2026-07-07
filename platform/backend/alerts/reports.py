"""
Reportes en lenguaje plano para Slack y el chatbot.

Dos productos:
1. Digest de scraper: cuando una corrida trae registros NUEVOS, un resumen
   narrativo de máximo 200 palabras en español neutro, sin tecnicismos.
2. Reporte de situación: panorama completo del valle bajo demanda (endpoint
   o tool del chat) — riesgo por comuna, lluvia, eventos y sismos recientes.

Mismo patrón que agent/risk_explanations.py:
  - ANTHROPIC_API_KEY presente → redacta Claude (temperature baja).
  - Ausente o con error → template determinístico (el sistema nunca se cae
    por falta de LLM; el digest sale igual, solo menos narrativo).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Mismo patrón que agent/chat_rag.py: los scrapers corren standalone (sin el
# proceso de la API que ya cargó el .env), así que se carga aquí también.
_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_BACKEND_ENV, override=False)

logger = logging.getLogger(__name__)

COL_TZ = ZoneInfo("America/Bogota")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
_SOURCE_LABELS: dict[str, str] = {
    "siata": "SIATA (lluvia)",
    "siata_sismos": "SIATA (sismos)",
    "dagrd": "DAGRD (emergencias)",
    "ideam": "IDEAM (meteorología)",
    "medellin_datos": "Medellín Datos (cartografía)",
}


def _get_anthropic_client():
    from infrastructure.external.llm_client import get_anthropic_client

    return get_anthropic_client()


def _llm_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


_SUMMARY_SYSTEM = """Eres el redactor de avisos del sistema TEYVA (monitoreo de
riesgo de deslizamientos en Medellín). Resumes novedades para un canal de
Slack que leen operarios y personas sin formación técnica.

REGLAS ESTRICTAS:
1. Máximo {max_words} palabras. Español neutro, sin tecnicismos ni siglas sin explicar.
2. Usa SOLO los datos que se te dan. NUNCA inventes cifras, lugares ni fechas.
3. Empieza por lo más importante para la seguridad de las personas.
4. Si los datos son rutinarios, dilo con calma — no dramatices.
5. Responde SOLO con el texto del resumen, sin títulos ni markdown."""


async def _claude_summary(context: str, max_words: int) -> str | None:
    """Una llamada de redacción a Claude. None si falla (activa el template)."""
    try:
        client = _get_anthropic_client()
        response = await asyncio.to_thread(
            client.messages.create,
            model=ANTHROPIC_MODEL,
            max_tokens=400,
            temperature=0.3,
            system=_SUMMARY_SYSTEM.format(max_words=max_words),
            messages=[{"role": "user", "content": context}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Claude no disponible para el resumen (%s); usando template.", exc)
        return None


# ── 1) Digest de scraper ───────────────────────────────────────────────────────

def _template_digest(source: str, new_items: list[dict]) -> str:
    label = _SOURCE_LABELS.get(source, source)
    lines = [f"{label} registró {len(new_items)} novedad{'es' if len(new_items) != 1 else ''}:"]
    for item in new_items[:8]:
        titulo = str(item.get("titulo") or "registro nuevo")
        detalle = str(item.get("detalle") or "").strip()
        fecha = str(item.get("fecha") or "").strip()
        parts = [titulo]
        if detalle:
            parts.append(detalle)
        if fecha:
            parts.append(fecha)
        lines.append("• " + " — ".join(parts))
    if len(new_items) > 8:
        lines.append(f"…y {len(new_items) - 8} más.")
    return "\n".join(lines)


async def generate_scraper_digest(
    source: str, new_items: list[dict], *, max_words: int = 200
) -> str:
    """Resumen en lenguaje plano de los registros nuevos de una corrida."""
    if not new_items:
        return ""
    if _llm_available():
        label = _SOURCE_LABELS.get(source, source)
        item_lines = "\n".join(
            f"- {item.get('titulo', '')} | {item.get('detalle', '')} | {item.get('fecha', '')}"
            for item in new_items[:20]
        )
        context = (
            f"La fuente de datos «{label}» acaba de registrar {len(new_items)} "
            f"novedades en Medellín:\n{item_lines}\n\n"
            f"Redacta el resumen para el canal de avisos."
        )
        text = await _claude_summary(context, max_words)
        if text:
            return text
    return _template_digest(source, new_items)


def build_scraper_digest_payload(source: str, summary: str, n_items: int) -> dict:
    """Bloque de Slack del digest — 4º tipo de aviso (informativo, barra azul)."""
    label = _SOURCE_LABELS.get(source, source)
    now_col = datetime.now(COL_TZ).strftime("%Y-%m-%d %H:%M")
    return {
        "attachments": [
            {
                "color": "#3683F8",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"📥 Novedades — {label}"},
                    },
                    {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"{n_items} registro(s) nuevo(s) · {now_col} Colombia · Sistema TEYVA",
                            }
                        ],
                    },
                ],
            }
        ]
    }


# ── 2) Reporte de situación bajo demanda ───────────────────────────────────────

async def _collect_situation_data(session: AsyncSession) -> dict:
    """Junta el panorama actual con las mismas fuentes que usan API y alertas."""
    from domain.risk_rules import display_label, normalize_category
    from db.models import LandslideEvent, RiskPrediction, SeismicEvent
    from db.models.rainfall_timeseries import RainfallTimeseries

    now = datetime.now(timezone.utc)

    # Última predicción por comuna.
    subq = (
        select(RiskPrediction.commune_id, func.max(RiskPrediction.created_at).label("max_at"))
        .group_by(RiskPrediction.commune_id)
        .subquery()
    )
    preds = (
        (
            await session.execute(
                select(RiskPrediction).join(
                    subq,
                    (RiskPrediction.commune_id == subq.c.commune_id)
                    & (RiskPrediction.created_at == subq.c.max_at),
                )
            )
        )
        .scalars()
        .all()
    )
    by_cat: dict[str, int] = {}
    worst: list[tuple[str, float]] = []
    for p in preds:
        cat = normalize_category(p.risk_category)
        by_cat[cat] = by_cat.get(cat, 0) + 1
        if cat in ("alto", "critico") and p.risk_score is not None:
            worst.append((p.commune_id, float(p.risk_score)))
    worst.sort(key=lambda t: -t[1])

    # Lluvia de hoy (medianoche Colombia) por comuna.
    midnight_col = datetime.now(COL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    rain_rows = (
        await session.execute(
            select(RainfallTimeseries.commune_id, func.sum(RainfallTimeseries.precip_mm))
            .where(RainfallTimeseries.snapshot_at >= midnight_col.astimezone(timezone.utc))
            .group_by(RainfallTimeseries.commune_id)
        )
    ).all()
    max_rain = max((float(r[1] or 0.0) for r in rain_rows), default=0.0)

    # Eventos y sismos de la última semana.
    week_ago = now - timedelta(days=7)
    n_events = (
        await session.scalar(
            select(func.count()).select_from(LandslideEvent).where(LandslideEvent.ingested_at >= week_ago)
        )
    ) or 0
    seismic = (
        (
            await session.execute(
                select(SeismicEvent)
                .where(SeismicEvent.ingested_at >= now - timedelta(days=30))
                .order_by(SeismicEvent.event_local_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )

    return {
        "por_categoria": {display_label(k): v for k, v in sorted(by_cat.items())},
        "comunas_criticas": worst[:5],
        "lluvia_max_hoy_mm": round(max_rain, 1),
        "eventos_7d": int(n_events),
        "sismos_recientes": [
            {
                "epicentro": s.epicenter_label or "s/d",
                "magnitud": s.magnitude,
                "fecha": s.event_local_at.strftime("%Y-%m-%d %H:%M") if s.event_local_at else "s/d",
            }
            for s in seismic
        ],
    }


def _template_situation_report(data: dict) -> str:
    cats = ", ".join(f"{v} en {k}" for k, v in data["por_categoria"].items()) or "sin predicciones"
    lines = [
        "Reporte de situación TEYVA — "
        + datetime.now(COL_TZ).strftime("%Y-%m-%d %H:%M") + " (Colombia).",
        f"Comunas por nivel de riesgo: {cats}.",
        f"Lluvia máxima acumulada hoy: {data['lluvia_max_hoy_mm']} mm.",
        f"Eventos de emergencia registrados en la última semana: {data['eventos_7d']}.",
    ]
    if data["comunas_criticas"]:
        detalle = ", ".join(f"comuna {cid} ({score:.0%})" for cid, score in data["comunas_criticas"])
        lines.append(f"Mayor atención en: {detalle}.")
    if data["sismos_recientes"]:
        s = data["sismos_recientes"][0]
        lines.append(
            f"Último sismo registrado: {s['epicentro']}"
            + (f", magnitud {s['magnitud']}" if s["magnitud"] is not None else "")
            + f" ({s['fecha']})."
        )
    return "\n".join(lines)


async def generate_situation_report(
    session: AsyncSession, *, max_words: int = 200
) -> str:
    """Reporte de situación completo en lenguaje plano (para Slack o el chat)."""
    data = await _collect_situation_data(session)
    if _llm_available():
        context = (
            "Datos actuales del sistema de monitoreo de deslizamientos de Medellín:\n"
            f"- Comunas por nivel de riesgo: {data['por_categoria']}\n"
            f"- Comunas en alto/crítico (id, probabilidad): {data['comunas_criticas']}\n"
            f"- Lluvia máxima acumulada hoy: {data['lluvia_max_hoy_mm']} mm\n"
            f"- Eventos de emergencia en 7 días: {data['eventos_7d']}\n"
            f"- Sismos recientes: {data['sismos_recientes']}\n\n"
            "Redacta un reporte de situación para el equipo de gestión del riesgo."
        )
        text = await _claude_summary(context, max_words)
        if text:
            return text
    return _template_situation_report(data)


async def send_situation_report_to_slack(session: AsyncSession) -> bool:
    """Genera el reporte y lo publica en el webhook configurado."""
    from alerts.slack import _fire_slack, _get_webhook_url

    webhook_url = await _get_webhook_url(session)
    if not webhook_url:
        return False
    report = await generate_situation_report(session)
    payload = {
        "attachments": [
            {
                "color": "#2E7D32",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "📋 Reporte de Situación — TEYVA"},
                    },
                    {"type": "section", "text": {"type": "mrkdwn", "text": report}},
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": datetime.now(COL_TZ).strftime("%Y-%m-%d %H:%M")
                                + " Colombia · generado bajo demanda",
                            }
                        ],
                    },
                ],
            }
        ]
    }
    status, _ = await _fire_slack(webhook_url, payload)
    return status == "sent"


async def maybe_send_scraper_digest(
    session: AsyncSession, source: str, new_items: list[dict] | None
) -> None:
    """Publica el digest de una corrida con novedades. Nunca lanza: cualquier
    fallo aquí no debe tumbar el scraper que lo invocó."""
    if not new_items:
        return
    try:
        from alerts.slack import _fire_slack, _get_webhook_url

        webhook_url = await _get_webhook_url(session)
        if not webhook_url:
            return
        summary = await generate_scraper_digest(source, new_items)
        if not summary:
            return
        payload = build_scraper_digest_payload(source, summary, len(new_items))
        status, _ = await _fire_slack(webhook_url, payload)
        if status == "sent":
            logger.info("Digest de %s enviado a Slack (%d novedades)", source, len(new_items))
    except Exception:  # noqa: BLE001
        logger.exception("El digest de %s falló (no crítico)", source)
