"""
Soporte multimedia para alertas de Slack.

Slack tiene dos formas de publicar:
- Incoming Webhook (lo que ya tenemos): solo texto/blocks; NO sube imágenes,
  solo puede referenciar URLs de imagen públicas.
- Bot Token (xoxb-...) + files API: SÍ sube la imagen PNG y aparece inline en
  el canal. Es la forma profesional de mostrar gráficas generadas.

Este módulo implementa:
- Subida de imagen vía files API v2 (getUploadURLExternal → upload → complete).
- Helpers de enriquecimiento: explicación de riesgo, recomendación, link al
  dashboard y a la gráfica.

Si no hay SLACK_BOT_TOKEN configurado, el llamador hace fallback al webhook con
sparkline + texto (la imagen se referencia por URL si CHART_BASE_URL es pública).
"""

from __future__ import annotations

import logging
import os

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import normalize_category
from db.models.risk_explanation import RiskExplanation

logger = logging.getLogger(__name__)

_SLACK_API = "https://slack.com/api"


def bot_token() -> str | None:
    return os.getenv("SLACK_BOT_TOKEN") or None


def channel_id() -> str | None:
    return os.getenv("SLACK_CHANNEL_ID") or None


def dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "http://localhost:3000").rstrip("/")


def chart_base_url() -> str:
    """Base pública para servir gráficas. En local apunta al backend."""
    return os.getenv("CHART_BASE_URL", "http://localhost:8000").rstrip("/")


def chart_url(commune_id: str) -> str:
    return f"{chart_base_url()}/api/alerts/chart/{commune_id}"


# --- Recomendaciones por categoría (coherentes con el dashboard) ---
_RECOMMENDATIONS: dict[str, str] = {
    "bajo": "Condiciones estables. Mantener monitoreo rutinario.",
    "medio": "Vigilar evolución de la lluvia. Revisar canales de drenaje e informar a la comunidad.",
    "alto": "Activar protocolos preventivos. Inspeccionar laderas inestables y coordinar con el comité local de riesgo.",
    "critico": "Alerta máxima. Considerar evacuación preventiva en zonas vulnerables y notificar al DAGRD de inmediato.",
}


def recommendation_for(category: str | None) -> str:
    return _RECOMMENDATIONS.get(normalize_category(category), _RECOMMENDATIONS["medio"])


async def latest_explanation(db: AsyncSession, commune_id: str) -> tuple[str, dict | None] | None:
    """Última risk_explanation generada para la comuna.

    Retorna `(explanation_text, explanation_json)` — `explanation_json` es
    `None` si esa fila se generó antes de existir la columna, o si el
    template/LLM no logró producir una estructura confiable.
    """
    stmt = (
        select(RiskExplanation.explanation, RiskExplanation.explanation_json)
        .where(RiskExplanation.commune_id == str(commune_id))
        .order_by(RiskExplanation.generated_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None
    return row[0], row[1]


async def upload_chart_to_slack(
    png_bytes: bytes,
    filename: str,
    title: str,
    initial_comment: str,
) -> bool:
    """
    Sube una imagen PNG al canal usando la files API v2 de Slack.
    Requiere SLACK_BOT_TOKEN (scope files:write) y SLACK_CHANNEL_ID.
    Devuelve True si la imagen quedó publicada en el canal.
    """
    token = bot_token()
    channel = channel_id()
    if not token or not channel:
        return False

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # 1) Reservar URL de subida
            r1 = await client.get(
                f"{_SLACK_API}/files.getUploadURLExternal",
                headers=headers,
                params={"filename": filename, "length": str(len(png_bytes))},
            )
            d1 = r1.json()
            if not d1.get("ok"):
                logger.warning("Slack getUploadURLExternal falló: %s", d1.get("error"))
                return False
            upload_url = d1["upload_url"]
            file_id = d1["file_id"]

            # 2) Subir bytes del archivo
            r2 = await client.post(
                upload_url,
                files={"file": (filename, png_bytes, "image/png")},
            )
            if r2.status_code != 200:
                logger.warning("Slack upload bytes falló: HTTP %s", r2.status_code)
                return False

            # 3) Completar subida y publicar en el canal
            r3 = await client.post(
                f"{_SLACK_API}/files.completeUploadExternal",
                headers={**headers, "Content-Type": "application/json; charset=utf-8"},
                json={
                    "files": [{"id": file_id, "title": title}],
                    "channel_id": channel,
                    "initial_comment": initial_comment,
                },
            )
            d3 = r3.json()
            if not d3.get("ok"):
                logger.warning("Slack completeUploadExternal falló: %s", d3.get("error"))
                return False
            return True
    except Exception as exc:
        logger.warning("Error subiendo imagen a Slack: %s", exc)
        return False
