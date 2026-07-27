"""Agente: monitorea salud de APIs externas.

Cada 30 min (mismo que SIATA), hace un ping liviano a:
- ArcGIS (mapserver de Medellín — infrastructure/external/arcgis_client.py)
- OSRM (routing — infrastructure/external/osrm_client.py)
- Anthropic API (Claude)
- Slack webhook (si está configurado)

Reusa las URLs base de los clientes reales del proyecto en vez de endpoints
genéricos: pingear un servicio que el proyecto no usa (ej. geocode.arcgis.com
de Esri, que este proyecto nunca llama) da falsos positivos de caída.

Si una cae, alerta con el servicio específico y sugiere el fallback ya existente.

Corre via GitHub Actions cron, no bloquea nada.
"""

from __future__ import annotations

import logging
import os

import httpx

from db.session import AsyncSessionLocal
from infrastructure.external.arcgis_client import COMUNA_QUERY_URL
from infrastructure.external.osrm_client import OSRM_BASE_URL
from monitoring.notify import fire_agent_alert, log_agent_run
from scraper.common import httpx_client

AGENT_NAME = "external-api-health-monitor"

logger = logging.getLogger(__name__)

# Convención ArcGIS REST: pedir metadata del servicio en JSON es la forma
# estándar de verificar que un MapServer responde sin ejecutar una query real.
_ARCGIS_MAPSERVER_URL = COMUNA_QUERY_URL.rsplit("/query", 1)[0]

# Dos puntos reales dentro de Medellín (Poblado -> Laureles), mismo patrón de
# carga que un request de evacuación real — el demo público de OSRM no expone
# un endpoint /status.
_OSRM_TEST_ORIGIN = (6.2087, -75.5679)
_OSRM_TEST_DEST = (6.2444, -75.5900)


async def check_arcgis() -> tuple[bool, str]:
    """Verifica que el mapserver de Medellín (ArcGIS) responda."""
    try:
        async with httpx_client(timeout=5.0) as client:
            r = await client.get(_ARCGIS_MAPSERVER_URL, params={"f": "json"})
            ok = r.status_code == 200
            return ok, f"ArcGIS: {r.status_code}"
    except Exception as e:
        return False, f"ArcGIS: {str(e)}"


async def check_osrm() -> tuple[bool, str]:
    """Verifica OSRM con una ruta real corta (no hay endpoint /status público)."""
    lat1, lon1 = _OSRM_TEST_ORIGIN
    lat2, lon2 = _OSRM_TEST_DEST
    url = f"{OSRM_BASE_URL}/{lon1},{lat1};{lon2},{lat2}"
    try:
        async with httpx_client(timeout=10.0) as client:
            r = await client.get(url, params={"overview": "false"})
            ok = r.status_code == 200 and (r.json().get("code") == "Ok")
            return ok, f"OSRM: {r.status_code}"
    except Exception as e:
        return False, f"OSRM: {str(e)}"


async def check_anthropic() -> tuple[bool, str]:
    """Ping Anthropic API (requiere el header anthropic-version)."""
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return False, "ANTHROPIC_API_KEY not set"

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
            ok = r.status_code == 200
            return ok, f"Anthropic: {r.status_code}"
    except Exception as e:
        return False, f"Anthropic: {str(e)}"


async def check_slack() -> tuple[bool, str]:
    """Validate Slack webhook if configured."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return True, "Slack: Not configured (skipped)"

    try:
        async with httpx_client(timeout=5.0) as client:
            # Do a HEAD request to check if webhook is reachable
            r = await client.head(webhook_url)
            ok = r.status_code in (200, 405)  # 405 is OK for HEAD on POST endpoint
            return ok, f"Slack: {r.status_code}"
    except Exception as e:
        return False, f"Slack: {str(e)}"


async def _recovered_since_last_run(session) -> bool:
    """True si la corrida anterior NO estaba en ok (o sea: esto es una recuperación).

    Sin esto, tras una caída el servicio volvería en silencio y quien vio la
    alerta roja nunca sabría que ya se resolvió.
    """
    from sqlalchemy import select

    from db.models.agent_run_log import AgentRunLog

    result = await session.execute(
        select(AgentRunLog.status)
        .where(AgentRunLog.agent_name == AGENT_NAME)
        .order_by(AgentRunLog.created_at.desc())
        .limit(1)
    )
    last_status = result.scalar_one_or_none()
    return last_status is not None and last_status != "ok"


async def run() -> None:
    """Run all API health checks."""
    checks = {
        "ArcGIS": await check_arcgis(),
        "OSRM": await check_osrm(),
        "Anthropic": await check_anthropic(),
        "Slack": await check_slack(),
    }

    failed = {name: msg for name, (ok, msg) in checks.items() if not ok}
    status = "critical" if failed else "ok"

    summary = f"API health check: {status.upper()} ({len(checks) - len(failed)}/{len(checks)} UP)"

    try:
        async with AsyncSessionLocal() as session:
            detail = {name: msg for name, (_, msg) in checks.items()}
            if failed:
                detail["failed_services"] = list(failed.keys())
                detail["fallback_note"] = (
                    "Claude -> Ollama fallback activo; verificar ENABLE_RAG, LLM_PROVIDER"
                )

            # Corre cada 30 min: mandar a Slack también cuando todo está OK
            # eran ~48 mensajes verdes al día, y con ese ruido las alertas
            # reales se pierden. En verde solo se registra en agent_run_logs;
            # se avisa al caer Y al recuperarse (para ver el "ya volvió").
            if failed or await _recovered_since_last_run(session):
                await fire_agent_alert(
                    session,
                    agent_name=AGENT_NAME,
                    status=status,
                    summary=summary,
                    detail=detail if failed else None,
                )
            else:
                await log_agent_run(
                    session,
                    agent_name=AGENT_NAME,
                    status=status,
                    summary=summary,
                    detail=detail,
                )
    except Exception as e:
        logger.exception("API health check failed: %s", e)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
