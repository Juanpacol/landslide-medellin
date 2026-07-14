"""
analyst_agent.py — Generador automatizado de reportes basados en datos.

Produce reportes de situación, resúmenes ejecutivos y análisis comparativos
para equipos técnicos de gestión del riesgo.

Uso:
    from src.agents.analyst_agent import AnalystAgent
    agent = AnalystAgent()
    report = await agent.situation_report()
"""

from __future__ import annotations
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "platform" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class AnalystAgent:
    """
    Agente analista TEYVA para generación automatizada de reportes.

    Consulta la base de datos en tiempo real y genera reportes estructurados
    sobre el estado de riesgo, eventos recientes y tendencias de precipitación.
    """

    async def situation_report(self) -> str:
        """
        Genera un reporte de situación completo del valle en lenguaje plano.

        Incluye: comunas por nivel de riesgo, lluvia del día, eventos de la
        semana y sismos recientes.
        """
        from agent.rag_tools import get_situation_report  # type: ignore
        return await get_situation_report()

    async def top_risk_communes(self, n: int = 5) -> list[dict]:
        """
        Retorna las N comunas con mayor riesgo actual.

        Args:
            n: Número de comunas a retornar (default 5).
        """
        from agent.tools import get_top_risk_comunas  # type: ignore
        from db.session import AsyncSessionLocal  # type: ignore
        async with AsyncSessionLocal() as db:
            return await get_top_risk_comunas(n, db)

    async def scraper_health_report(self) -> str:
        """Retorna el estado de salud de todas las fuentes de datos."""
        from agent.rag_tools import get_scraper_health  # type: ignore
        return await get_scraper_health()

    async def rainfall_alert_check(self, commune_id: str, threshold_mm: float = 80.0) -> bool:
        """
        Verifica si la precipitación acumulada en 7 días supera el umbral.

        Args:
            commune_id:    ID de la comuna ("1"–"21").
            threshold_mm:  Umbral de precipitación en mm (default 80 mm).

        Returns:
            True si la precipitación supera el umbral, False si no.
        """
        from agent.rag_tools import get_rainfall_timeseries  # type: ignore
        result = await get_rainfall_timeseries(commune=commune_id, days=7)
        # Parsear el total del texto retornado
        try:
            total = float([w for w in result.split() if w.replace(".", "").isdigit()][0])
            return total >= threshold_mm
        except (IndexError, ValueError):
            return False
