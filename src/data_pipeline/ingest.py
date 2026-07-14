"""
ingest.py — Conexión con APIs de datos abiertos.

Módulo de alto nivel para disparar la ingesta de datos desde las
fuentes institucionales. Delega en los scrapers de platform/backend/scraper/.

Uso:
    from src.data_pipeline.ingest import DataIngester
    ingester = DataIngester()
    await ingester.run_all()
"""

from __future__ import annotations
import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "platform" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class DataIngester:
    """Orquestador de ingesta de todas las fuentes de datos abiertos."""

    async def run_siata(self) -> dict:
        """Ejecuta el scraper de SIATA (lluvia + geotécnica)."""
        from scraper.siata import run as _run  # type: ignore
        return await _run()

    async def run_dagrd(self) -> dict:
        """Ejecuta el scraper de DAGRD (eventos de emergencia)."""
        from scraper.dagrd import run as _run  # type: ignore
        return await _run()

    async def run_ideam(self) -> dict:
        """Ejecuta el scraper de IDEAM (pronóstico meteorológico)."""
        from scraper.ideam import run as _run  # type: ignore
        return await _run()

    async def run_medellin(self) -> dict:
        """Ejecuta el scraper de GeoMedellín (datos territoriales)."""
        from scraper.medellin_datos import run as _run  # type: ignore
        return await _run()

    async def run_all(self) -> dict[str, dict]:
        """
        Ejecuta todos los scrapers en paralelo.

        Returns:
            Diccionario con el resultado de cada fuente:
            {"siata": {...}, "dagrd": {...}, "ideam": {...}, "medellin": {...}}
        """
        results = await asyncio.gather(
            self.run_siata(),
            self.run_dagrd(),
            self.run_ideam(),
            self.run_medellin(),
            return_exceptions=True,
        )
        sources = ["siata", "dagrd", "ideam", "medellin"]
        return {src: res for src, res in zip(sources, results)}

    def get_latest_status(self) -> list[dict]:
        """
        Retorna el estado del último run de cada scraper desde scraping_logs.
        """
        import asyncio
        from agent.rag_tools import get_scraper_health  # type: ignore
        return asyncio.run(get_scraper_health())
