"""
RAG Tools — Lógica central de las herramientas del chatbot TEYVA.

Estas funciones son la ÚNICA fuente de verdad de la lógica de negocio de cada
tool. Las consumen dos clientes:
  1. agent/chat_rag.py   → loop de tool-calling con Ollama (local)
  2. agent/mcp_server.py → servidor FastMCP (futuro: GPT-4o-mini vía OpenRouter)

Cada tool devuelve un STRING legible (el resultado se le devuelve al modelo como
texto). Las tools de base de datos abren su propia sesión para ser autocontenidas.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
from datetime import datetime, timedelta, timezone
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from sqlalchemy import func, select

from agent.tools import (
    commune_display_name,
    find_communes_in_text,
    get_top_risk_comunas,
    resolve_commune_id,
)
from domain.risk_rules import display_label, risk_level_from_score
from domain.validation import validate_citizen_report
from errors.error_handler import ValidationError
from db.models import LandslideEvent, RainfallTimeseries, RiskPrediction, ScrapingLog
from db.session import AsyncSessionLocal

# Fuentes válidas del RAG (para validar el filtro).
RAG_SOURCES = ("siata_hidromet", "siata_geotecnia", "dagrd_eventos", "medellin_comunas")


# ---------------------------------------------------------------------------
# Colector de fuentes consultadas (por request, seguro entre tareas async)
# ---------------------------------------------------------------------------
# Cada llamada a search_knowledge registra aquí las fuentes de los chunks que
# realmente recuperó, como pares (referencia_archivo, página). chat_rag lo lee
# al final para anexar "Fuentes consultadas" con las páginas agregadas por archivo.
_sources_ctx: contextvars.ContextVar[list[tuple[str, int]] | None] = contextvars.ContextVar(
    "rag_sources", default=None
)

# Solo estas fuentes provienen de PDFs paginados; en las demás la página no aplica.
_PAGED_SOURCES = ("siata_hidromet", "siata_geotecnia")


def reset_sources() -> None:
    """Inicia un colector de fuentes nuevo para el request actual."""
    _sources_ctx.set([])


def _citation_base(meta: dict[str, Any]) -> str:
    """Referencia a nivel de archivo (sin página)."""
    src = meta.get("source_id", "")
    date = meta.get("date", "")
    zone = meta.get("zone", "")
    pdf = meta.get("source_pdf", "")
    url = meta.get("url", "")
    title = meta.get("title", "")

    if src == "siata_hidromet":
        ref = f"Reporte semanal SIATA HIDROMET ({date})"
        return f"{ref} — {pdf}" if pdf else ref
    if src == "siata_geotecnia":
        ref = f"Hoja de Vida geotécnica de {zone}" if zone else "Hoja de Vida geotécnica SIATA"
        return f"{ref} — {pdf}" if pdf else ref
    if src == "dagrd_eventos":
        ref = f"Reporte DAGRD ({date}): {title}".strip().rstrip(":")
        return f"{ref} — {url}" if url else ref
    if src == "medellin_comunas":
        return (
            f"Perfil de riesgo de {zone} (Alcaldía de Medellín, ArcGIS)"
            if zone
            else "Perfil de riesgo por comuna (Alcaldía de Medellín, ArcGIS)"
        )
    return src or "Fuente desconocida"


def _page_of(meta: dict[str, Any]) -> int:
    """Página del chunk si la fuente es un PDF paginado; 0 si no aplica."""
    if meta.get("source_id") not in _PAGED_SOURCES:
        return 0
    try:
        return int(meta.get("page") or 0)
    except (TypeError, ValueError):
        return 0


def format_citation(meta: dict[str, Any]) -> str:
    """Cita legible de un chunk, con página si aplica (para uso inline)."""
    base = _citation_base(meta)
    page = _page_of(meta)
    return f"{base} (pág. {page})" if page > 0 else base


def _record_source(meta: dict[str, Any]) -> None:
    bag = _sources_ctx.get()
    if bag is not None:
        bag.append((_citation_base(meta), _page_of(meta)))


def get_sources() -> list[str]:
    """
    Fuentes consultadas, una línea por archivo, con las páginas agregadas.
    Mantiene el orden de primera aparición.
    """
    bag = _sources_ctx.get()
    if not bag:
        return []
    order: list[str] = []
    pages: dict[str, set[int]] = {}
    for base, page in bag:
        if base not in pages:
            pages[base] = set()
            order.append(base)
        if page > 0:
            pages[base].add(page)

    out: list[str] = []
    for base in order:
        ps = sorted(pages[base])
        if not ps:
            out.append(base)
        elif len(ps) == 1:
            out.append(f"{base} (pág. {ps[0]})")
        else:
            out.append(f"{base} (págs. {', '.join(map(str, ps))})")
    return out


def _resolve_commune_loose(value: str) -> Optional[str]:
    """
    Resuelve un commune_id tolerando entradas sucias del modelo.

    Primero intenta el resolvedor exacto; si falla (p.ej. el modelo manda
    "[Zona: Comuna 13 | Municipio: Medellín]"), extrae la comuna del texto libre.
    """
    cid = resolve_commune_id(value)
    if cid:
        return cid
    hits = find_communes_in_text(value)
    return hits[0] if hits else None


# ---------------------------------------------------------------------------
# TOOL 1 — Búsqueda semántica en el RAG (ChromaDB)
# ---------------------------------------------------------------------------
async def search_knowledge(query: str, source: Optional[str] = None) -> str:
    """Busca en la base de conocimiento (2127 chunks de SIATA, DAGRD, comunas)."""
    from rag import chroma_store

    if source and source not in RAG_SOURCES:
        return f"Fuente inválida '{source}'. Válidas: {', '.join(RAG_SOURCES)}."

    # Si la query menciona una zona geotécnica conocida (ej. "Villatina"),
    # filtra a esa zona para no mezclar zonas vecinas con boilerplate similar.
    zone = chroma_store.detect_zone(query)

    # La búsqueda embebe la query (bloqueante) → corre en thread aparte.
    try:
        results = await asyncio.to_thread(chroma_store.search, query, source, 5, zone)
    except Exception as e:  # noqa: BLE001
        return f"No se pudo consultar la base de conocimiento: {e}"

    if not results:
        return "No se encontró información relevante en la base de conocimiento."

    # Envuelve los resultados en XML tags para claridad estructural
    lines = ["<retrieved_documents>"]
    lines.append(f"Resultados de la base de conocimiento para «{query}»:")
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        citation = format_citation(meta)
        _record_source(meta)  # acumula (archivo, página) para el footer
        text = " ".join(r.get("text", "").split())  # colapsa espacios
        if len(text) > 600:
            text = text[:600] + "…"
        # La línea FUENTE permite que el modelo cite inline si quiere.
        lines.append(f'\n<document id="{i}">')
        lines.append(f"<source>{citation}</source>")
        lines.append(f"<content>{text}</content>")
        lines.append("</document>")
    lines.append("</retrieved_documents>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TOOL 2 — Predicciones de riesgo actuales (PostgreSQL)
# ---------------------------------------------------------------------------
async def get_risk_predictions(commune: Optional[str] = None) -> str:
    """Predicciones de riesgo de deslizamiento más recientes por comuna."""
    async with AsyncSessionLocal() as db:
        if commune:
            cid = _resolve_commune_loose(commune)
            if cid is None:
                return f"No reconozco la comuna «{commune}»."
            stmt = (
                select(RiskPrediction)
                .where(RiskPrediction.commune_id == cid)
                .order_by(RiskPrediction.created_at.desc(), RiskPrediction.id.desc())
                .limit(1)
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None or row.risk_score is None:
                return f"No hay predicción reciente para {commune_display_name(cid)}."
            nivel = display_label(row.risk_category or risk_level_from_score(row.risk_score))
            cuando = _humanize_age(row.created_at)
            return f"Comuna {commune_display_name(cid)}: riesgo {nivel}. {cuando}."

        # Sin comuna → top 5 de mayor riesgo.
        top = await get_top_risk_comunas(5, db)
        if not top:
            return "No hay predicciones de riesgo cargadas en este momento."
        partes = [
            f"{r['nombre']}: riesgo {display_label(r['risk_category'] or risk_level_from_score(r['risk_score']))}"
            for r in top
        ]
        return "Comunas con mayor riesgo ahora: " + "; ".join(partes) + "."


# ---------------------------------------------------------------------------
# TOOL 3 — Eventos recientes de deslizamiento (PostgreSQL)
# ---------------------------------------------------------------------------
async def get_recent_events(days: int = 7, commune: Optional[str] = None) -> str:
    """Eventos de deslizamiento/emergencia registrados recientemente."""
    days = max(1, min(int(days), 365))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        le = LandslideEvent
        stmt = select(le).where(le.ingested_at >= cutoff)
        resolved_cid: Optional[str] = None
        if commune:
            resolved_cid = _resolve_commune_loose(commune)
            if resolved_cid is None:
                return f"No reconozco la comuna «{commune}»."
            stmt = stmt.where(le.commune_id == resolved_cid)
        stmt = stmt.order_by(le.ingested_at.desc()).limit(15)
        rows = (await db.execute(stmt)).scalars().all()

        if not rows:
            ambito = f" en {commune_display_name(resolved_cid)}" if resolved_cid else ""
            return f"No hay eventos registrados en los últimos {days} días{ambito}."

        lines = [f"Eventos en los últimos {days} días ({len(rows)}):"]
        for r in rows:
            nombre = (
                commune_display_name(str(r.commune_id)) if r.commune_id else "ubicación sin asignar"
            )
            fecha = r.fecha or "fecha s/d"
            tipo = r.tipo_emergencia or "evento"
            lines.append(f"- {fecha} | {nombre} | {tipo}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# TOOL 4 — Serie temporal de lluvia (PostgreSQL)
# ---------------------------------------------------------------------------
async def get_rainfall_timeseries(commune: str, days: int = 7) -> str:
    """Lluvia acumulada reciente de una comuna a partir de los sensores SIATA."""
    cid = _resolve_commune_loose(commune)
    if cid is None:
        return f"No reconozco la comuna «{commune}»."
    days = max(1, min(int(days), 90))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        rt = RainfallTimeseries
        stmt = (
            select(
                func.count(rt.id),
                func.sum(rt.precip_mm),
                func.max(rt.precip_mm),
                func.max(rt.snapshot_at),
            )
            .where(rt.commune_id == cid)
            .where(rt.snapshot_at >= cutoff)
        )
        n, total, pico, ultimo = (await db.execute(stmt)).one()

        if not n:
            return f"No hay datos de lluvia de los últimos {days} días para {commune_display_name(cid)}."

        total = round(float(total or 0), 1)
        pico = round(float(pico or 0), 1)
        cuando = _humanize_age(ultimo)
        return (
            f"Lluvia en {commune_display_name(cid)} (últimos {days} días): "
            f"acumulado ~{total} mm en {n} mediciones, pico de {pico} mm. {cuando}."
        )


# ---------------------------------------------------------------------------
# TOOL 5 — Salud de los scrapers (PostgreSQL)
# ---------------------------------------------------------------------------
async def get_scraper_health() -> str:
    """Estado de las 4 fuentes de datos (SIATA, IDEAM, DAGRD, Medellín)."""
    async with AsyncSessionLocal() as db:
        sub = (
            select(ScrapingLog.source, func.max(ScrapingLog.created_at).label("mx"))
            .group_by(ScrapingLog.source)
            .subquery()
        )
        stmt = select(ScrapingLog).join(
            sub,
            (ScrapingLog.source == sub.c.source) & (ScrapingLog.created_at == sub.c.mx),
        )
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            return "No hay registros de scrapers todavía."

        lines = ["Estado de las fuentes de datos:"]
        for r in sorted(rows, key=lambda x: x.source):
            estado = "✅" if r.status == "ok" else "⚠️"
            cuando = _humanize_age(r.created_at)
            lines.append(
                f"{estado} {r.source}: {r.status} ({r.records_valid or 0} válidos). {cuando}."
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utilidad de fechas
# ---------------------------------------------------------------------------
def _humanize_age(value: Any) -> str:
    """Formats a timestamp as a relative age string in Spanish (e.g. "hace 5 min")."""
    if not value:
        return "sin fecha"
    try:
        dt = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
    except (ValueError, TypeError):
        return "hace poco"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    mins = max(1, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))
    if mins < 60:
        return f"hace {mins} min"
    if mins < 1440:
        return f"hace {mins // 60} h"
    return f"hace {mins // 1440} días"


# ---------------------------------------------------------------------------
# TOOL 6 — Reporte ciudadano (PostgreSQL, tabla citizen_reports)
# ---------------------------------------------------------------------------
# El session_id de la conversación viaja por contextvar (mismo patrón que el
# colector de fuentes): chat_rag lo fija al inicio de cada request.
_report_session_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "report_session", default=None
)


def set_report_session(session_id: str | None) -> None:
    """Sets the citizen-report session id for the current request's contextvar."""
    _report_session_ctx.set(session_id)


async def report_incident(commune: str, descripcion: str, barrio: Optional[str] = None) -> str:
    """Registra un avistamiento reportado por un ciudadano.

    Entra a `citizen_reports` con status `pending_review` — tabla SEPARADA de
    los eventos oficiales DAGRD, así que NO alimenta el modelo ni dispara
    alertas hasta que un operario lo verifique.
    """
    from db.models.citizen_report import CitizenReport

    try:
        descripcion = validate_citizen_report(descripcion, commune)
    except ValidationError as exc:
        # Se atrapa aquí (en vez de dejarla burbujear) para devolver el
        # mensaje amigable exacto que ya usa el chat, no un 422 crudo — esta
        # función corre dentro del loop de tool-calling, no de una ruta HTTP.
        return str(exc)
    cid = _resolve_commune_loose(commune)
    if cid is None:
        return f"No reconozco la comuna «{commune}». Dime el nombre o número de tu comuna."

    async with AsyncSessionLocal() as db:
        row = CitizenReport(
            commune_id=cid,
            barrio=(barrio or "").strip() or None,
            descripcion=descripcion[:2000],
            status="pending_review",
            session_id=_report_session_ctx.get(),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

    lugar = commune_display_name(cid) + (f", barrio {barrio}" if barrio else "")
    return (
        f"Reporte #{row.id} registrado para {lugar}. Quedó EN REVISIÓN: el equipo "
        f"de gestión del riesgo lo verificará antes de tomar acciones. "
        f"Si es una emergencia en curso, llama YA al DAGRD 4444444 o a Bomberos "
        f"119 — este reporte no reemplaza la línea de emergencia."
    )


# ---------------------------------------------------------------------------
# TOOL 7 — Reporte de situación en lenguaje plano
# ---------------------------------------------------------------------------
async def get_situation_report() -> str:
    """Panorama actual del valle (riesgo, lluvia, eventos, sismos) en lenguaje plano."""
    from alerts.reports import generate_situation_report

    async with AsyncSessionLocal() as db:
        return await generate_situation_report(db)


# ---------------------------------------------------------------------------
# TOOL 8 — Rutas de evacuación (MVP, OpenStreetMap + OSRM)
# ---------------------------------------------------------------------------
async def get_evacuation_routes(commune: str) -> str:
    """Zonas seguras candidatas más cercanas a una comuna, con distancia y
    tiempo caminando. MVP sin validar por Defensoría/DAGRD."""
    cid = _resolve_commune_loose(commune)
    if cid is None:
        return f"No reconozco la comuna «{commune}»."

    from alerts.evacuation import get_evacuation_routes as _get_routes

    async with AsyncSessionLocal() as db:
        result = await _get_routes(db, cid)

    if result.get("error"):
        return f"{result['error']}"

    nombre = commune_display_name(cid)
    lines = [f"Zonas seguras candidatas cerca de {nombre} (sin validar por Defensoría/DAGRD):"]
    for z in result.get("zones", []):
        tiempo = (
            f"{z['duration_walking_min']:.0f} min caminando"
            if z.get("duration_walking_min")
            else f"~{z['distance_straight_km']} km en línea recta"
        )
        lines.append(f"- {z['nombre']} ({z['tipo']}): {tiempo}")
    lines.append("Recuerda: en caso de emergencia real, contacta primero a DAGRD 4444444.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Esquemas de tools (formato OpenAI / Ollama) + dispatcher
# ---------------------------------------------------------------------------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Busca información en la base de conocimiento de TEYVA: reportes "
                "semanales de lluvia de SIATA, fichas geotécnicas de zonas de "
                "deslizamiento, eventos históricos de DAGRD y perfiles de riesgo "
                "por comuna. Úsala para preguntas sobre lluvia histórica, contexto, "
                "geología, antecedentes o explicaciones técnicas. La búsqueda elige "
                "automáticamente la mejor fuente; solo pasa la consulta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Consulta en lenguaje natural"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_risk_predictions",
            "description": (
                "Devuelve la predicción de riesgo de deslizamiento ACTUAL del modelo "
                "ML. Si se da una comuna, devuelve la suya; si no, el top de mayor riesgo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commune": {
                        "type": "string",
                        "description": "Nombre o número de comuna (opcional)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_events",
            "description": "Lista eventos de deslizamiento/emergencia registrados recientemente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Días hacia atrás (default 7)"},
                    "commune": {"type": "string", "description": "Filtra por comuna (opcional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rainfall_timeseries",
            "description": "Lluvia acumulada reciente de una comuna según sensores SIATA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commune": {"type": "string", "description": "Nombre o número de comuna"},
                    "days": {"type": "integer", "description": "Días hacia atrás (default 7)"},
                },
                "required": ["commune"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scraper_health",
            "description": "Estado de salud de las fuentes de datos (SIATA, IDEAM, DAGRD, Medellín, sismos).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_incident",
            "description": (
                "Registra un reporte ciudadano de una situación de riesgo observada "
                "(grietas, movimiento de tierra, agua turbia en la ladera, muros "
                "inclinados). Úsala cuando el usuario describe algo que está viendo "
                "y quiere reportarlo. El reporte queda en revisión para el equipo de "
                "gestión del riesgo — NO es la línea de emergencia."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commune": {
                        "type": "string",
                        "description": "Nombre o número de la comuna donde se observa",
                    },
                    "descripcion": {
                        "type": "string",
                        "description": "Qué está observando la persona, en sus palabras",
                    },
                    "barrio": {"type": "string", "description": "Barrio específico (opcional)"},
                },
                "required": ["commune", "descripcion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_situation_report",
            "description": (
                "Genera un reporte de situación completo del valle en lenguaje plano: "
                "comunas por nivel de riesgo, lluvia de hoy, eventos de la semana y "
                "sismos recientes. Úsala cuando pidan 'un resumen de la situación', "
                "'cómo está todo hoy' o un panorama general."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_evacuation_routes",
            "description": (
                "Devuelve zonas seguras candidatas (parques, colegios, estadios) "
                "más cercanas a una comuna, con tiempo caminando. Úsala cuando "
                "pregunten '¿adónde evacuo?', 'rutas seguras' o similar. MVP sin "
                "validar por Defensoría/DAGRD — siempre menciona la línea de "
                "emergencia DAGRD 4444444 para casos reales."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commune": {"type": "string", "description": "Nombre o número de comuna"},
                },
                "required": ["commune"],
            },
        },
    },
]

# Mapa nombre → función.
_DISPATCH: dict[str, Callable[..., Awaitable[str]]] = {
    "search_knowledge": search_knowledge,
    "get_risk_predictions": get_risk_predictions,
    "get_recent_events": get_recent_events,
    "get_rainfall_timeseries": get_rainfall_timeseries,
    "get_scraper_health": get_scraper_health,
    "report_incident": report_incident,
    "get_situation_report": get_situation_report,
    "get_evacuation_routes": get_evacuation_routes,
}


async def call_tool(name: str, arguments: dict[str, Any] | str | None) -> str:
    """Ejecuta una tool por nombre con sus argumentos (dict o JSON string)."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return f"Herramienta desconocida: {name}"
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = {}
    arguments = arguments or {}
    try:
        return await fn(**arguments)
    except TypeError as e:
        return f"Argumentos inválidos para {name}: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Error ejecutando {name}: {e}"
