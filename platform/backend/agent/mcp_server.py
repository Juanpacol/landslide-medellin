"""
FastMCP Server — Expone las tools de TEYVA vía Model Context Protocol.

Envuelve la lógica de agent/rag_tools.py (la misma que usa el chat local con
Ollama) como tools MCP. Esto permite que un modelo externo —GPT-4o-mini vía
OpenRouter— acceda a la base de conocimiento (ChromaDB) y a la base de datos
(PostgreSQL) cuando se conecte la API key.

Ejecutar:
    # stdio (default, para clientes MCP locales)
    python -m agent.mcp_server

    # HTTP (para acceso remoto / OpenRouter)
    python -m agent.mcp_server --http --port 8001

Las tools son idénticas a las del chat local; la lógica vive en un solo lugar.
"""

from __future__ import annotations

import argparse
from typing import Optional

from fastmcp import FastMCP

from agent import rag_tools

mcp = FastMCP("teyva-knowledge")


@mcp.tool
async def search_knowledge(query: str, source: Optional[str] = None) -> str:
    """Busca en la base de conocimiento de TEYVA (SIATA, geotecnia, DAGRD, comunas).

    Args:
        query: Consulta en lenguaje natural.
        source: Filtra por fuente (siata_hidromet, siata_geotecnia,
                dagrd_eventos, medellin_comunas). Opcional.
    """
    return await rag_tools.search_knowledge(query, source)


@mcp.tool
async def get_risk_predictions(commune: Optional[str] = None) -> str:
    """Predicción de riesgo de deslizamiento ACTUAL del modelo ML.

    Args:
        commune: Nombre o número de comuna. Si se omite, devuelve el top de mayor riesgo.
    """
    return await rag_tools.get_risk_predictions(commune)


@mcp.tool
async def get_recent_events(days: int = 7, commune: Optional[str] = None) -> str:
    """Eventos de deslizamiento/emergencia registrados recientemente.

    Args:
        days: Días hacia atrás (default 7).
        commune: Filtra por comuna. Opcional.
    """
    return await rag_tools.get_recent_events(days, commune)


@mcp.tool
async def get_rainfall_timeseries(commune: str, days: int = 7) -> str:
    """Lluvia acumulada reciente de una comuna según sensores SIATA.

    Args:
        commune: Nombre o número de comuna.
        days: Días hacia atrás (default 7).
    """
    return await rag_tools.get_rainfall_timeseries(commune, days)


@mcp.tool
async def get_scraper_health() -> str:
    """Estado de salud de las 4 fuentes de datos (SIATA, IDEAM, DAGRD, Medellín)."""
    return await rag_tools.get_scraper_health()


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor FastMCP de TEYVA")
    parser.add_argument("--http", action="store_true", help="Sirve por HTTP en vez de stdio")
    parser.add_argument("--port", type=int, default=8001, help="Puerto HTTP (default 8001)")
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
