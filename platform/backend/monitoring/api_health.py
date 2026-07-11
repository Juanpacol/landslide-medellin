"""Agente: monitorea salud de APIs externas.

Cada 30 min (mismo que SIATA), hace un ping liviano a:
- ArcGIS (geocoding)
- OSRM (routing)
- Anthropic API (Claude)
- Slack webhook (si está configurado)

Si una cae, alerta con el servicio específico y sugiere el fallback ya existente.

Corre via GitHub Actions cron, no bloquea nada.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from db.session import AsyncSessionLocal
from monitoring.notify import fire_agent_alert
from scraper.common import httpx_client

logger = logging.getLogger(__name__)


async def check_arcgis() -> tuple[bool, str]:
    """Ping ArcGIS geocoding service."""
    try:
        async with httpx_client(timeout=5.0) as client:
            r = await client.get(
                "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/ping"
            )
            ok = r.status_code == 200
            return ok, f"ArcGIS: {r.status_code}"
    except Exception as e:
        return False, f"ArcGIS: {str(e)}"


async def check_osrm() -> tuple[bool, str]:
    """Ping OSRM routing service."""
    try:
        async with httpx_client(timeout=5.0) as client:
            # OSRM status endpoint
            r = await client.get("http://router.project-osrm.org/status")
            ok = r.status_code == 200
            return ok, f"OSRM: {r.status_code}"
    except Exception as e:
        return False, f"OSRM: {str(e)}"


async def check_anthropic() -> tuple[bool, str]:
    """Ping Anthropic API."""
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return False, "ANTHROPIC_API_KEY not set"

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key},
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

            await fire_agent_alert(
                session,
                agent_name="external-api-health-monitor",
                status=status,
                summary=summary,
                detail=detail if failed else None,
            )
    except Exception as e:
        logger.exception("API health check failed: %s", e)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
