"""
Risk Explanation Service

Generates natural-language explanations for commune risk scores.

Behavior:
  - OPENROUTER_API_KEY set  → calls GPT-4 Mini via OpenRouter with tool use
  - OPENROUTER_API_KEY unset → builds a deterministic template explanation
    (honest, data-driven, zero hallucinations possible)

Prompt engineering techniques used:
  - Role priming + negative constraints ("NUNCA inventes")
  - Tool-use grounding (model must call tools before answering)
  - Low temperature (0.3) for consistency
  - Strict token budget (max_tokens=200)
  - Structured human message with all numeric context explicit
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import RISK_THRESHOLD_ALTO, RISK_THRESHOLD_CRITICO, RISK_THRESHOLD_MEDIO
from db.models.ml_feature import MLFeature
from db.models.risk_prediction import RiskPrediction

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_OPENROUTER_BASE = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

_NOMBRES: dict[str, str] = {
    "1": "Popular", "2": "Santa Cruz", "3": "Manrique", "4": "Aranjuez",
    "5": "Castilla", "6": "Doce de Octubre", "7": "Robledo", "8": "Villa Hermosa",
    "9": "Buenos Aires", "10": "La Candelaria", "11": "Laureles-Estadio",
    "12": "La América", "13": "San Javier", "14": "El Poblado", "15": "Guayabal",
    "16": "Belén", "50": "Palmitas", "60": "San Cristóbal", "70": "Altavista",
    "80": "San Antonio de Prado", "90": "Santa Elena",
}

_IS_LADERA: dict[str, bool] = {
    "1": True, "2": True, "3": True, "4": False, "5": False,
    "6": True, "7": True, "8": True, "9": True, "10": False,
    "11": False, "12": False, "13": True, "14": False, "15": False,
    "16": True, "50": True, "60": True, "70": True, "80": False, "90": True,
}

# ── System prompt (applied once, high token efficiency) ────────────────────────

_SYSTEM_PROMPT = """Eres un experto en análisis de riesgo de deslizamientos para el sistema TEYVA de Medellín, Colombia.

MISIÓN: Generar una explicación clara de 2-3 oraciones sobre POR QUÉ una comuna tiene su nivel de riesgo actual.

REGLAS ESTRICTAS:
1. Usa SOLO los datos numéricos que el usuario te proporciona o que obtienes vía tools.
2. NUNCA inventes valores, eventos, fechas o predicciones no presentes en los datos.
3. Máximo 100 palabras. Mínimo 30 palabras.
4. Estructura: factor principal → factor secundario → recomendación operativa.
5. Tono: técnico-operativo, directo. Urgente si categoría es "alto" o "critico".
6. NUNCA uses: "podría", "tal vez", "aparentemente", "posiblemente".
7. Siempre termina con una acción concreta para el operario.

CATEGORÍAS:
- bajo (<0.35): Monitoreo rutinario.
- medio (0.35-0.65): Vigilancia activa.
- alto (0.65-0.90): Alerta operativa — inspección de campo.
- critico (≥0.90): Acción inmediata — evaluar evacuación."""

# ── Tool definitions (OpenAI-compatible format for OpenRouter) ─────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_historical_trend",
            "description": (
                "Obtiene el historial de risk_score de los últimos N días para una comuna. "
                "Úsalo para determinar si el riesgo está subiendo, bajando o estable."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commune_id": {
                        "type": "string",
                        "description": "ID de la comuna (número como string, ej: '1', '13')"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Días atrás a consultar. Entre 1 y 30.",
                        "default": 7
                    }
                },
                "required": ["commune_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_events_count",
            "description": (
                "Obtiene el número de eventos de deslizamiento/emergencia registrados "
                "para una comuna en los últimos N días."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commune_id": {
                        "type": "string",
                        "description": "ID de la comuna"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Ventana de días a consultar. Default 30.",
                        "default": 30
                    }
                },
                "required": ["commune_id"]
            }
        }
    }
]

# ── Tool handlers (run against real DB) ───────────────────────────────────────

async def _handle_get_historical_trend(
    commune_id: str,
    days: int,
    db: AsyncSession,
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 30)))
    stmt = (
        select(RiskPrediction)
        .where(RiskPrediction.commune_id == commune_id)
        .where(RiskPrediction.created_at >= cutoff)
        .order_by(RiskPrediction.created_at.asc())
        .limit(30)
    )
    rows = (await db.execute(stmt)).scalars().all()

    series = [
        {"date": r.created_at.date().isoformat(), "score": round(float(r.risk_score), 3)}
        for r in rows
        if r.created_at and r.risk_score is not None
    ]

    if len(series) >= 2:
        delta = series[-1]["score"] - series[0]["score"]
        trend = "subiendo" if delta > 0.05 else "bajando" if delta < -0.05 else "estable"
    else:
        trend = "sin_datos_suficientes"

    return {
        "commune_id": commune_id,
        "days": days,
        "n_points": len(series),
        "trend": trend,
        "series": series[-7:],  # últimos 7 puntos máximo
    }


async def _handle_get_recent_events_count(
    commune_id: str,
    days: int,
    db: AsyncSession,
) -> dict[str, Any]:
    from db.models.landslide_event import LandslideEvent
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))
    stmt = (
        select(MLFeature.n_events_window)
        .where(MLFeature.commune_id == commune_id)
        .where(MLFeature.reference_date >= cutoff)
        .order_by(MLFeature.reference_date.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    n_events = int(row) if row is not None else 0

    return {"commune_id": commune_id, "days": days, "n_events": n_events}


async def _dispatch_tool(name: str, args: dict, commune_id: str, db: AsyncSession) -> dict[str, Any]:
    if name == "get_historical_trend":
        return await _handle_get_historical_trend(
            args.get("commune_id", commune_id),
            int(args.get("days", 7)),
            db,
        )
    if name == "get_recent_events_count":
        return await _handle_get_recent_events_count(
            args.get("commune_id", commune_id),
            int(args.get("days", 30)),
            db,
        )
    return {"error": f"Tool desconocida: {name}"}

# ── Template fallback (no API key needed) ──────────────────────────────────────

def _template_explanation(
    commune_id: str,
    nombre: str,
    risk_score: float,
    risk_category: str,
    precip_acum_mm: float,
    threshold_mm: float,
    n_events_7d: int,
    is_ladera: bool,
) -> str:
    """Genera explicación determinística basada en datos reales. Sin hallucinations."""

    cat = risk_category.lower().replace("í", "i")
    score_pct = round(risk_score * 100, 1)
    exceso = round(precip_acum_mm - threshold_mm, 1)
    terrain = "ladera" if is_ladera else "planicie"

    if cat == "critico":
        lluvia_frag = (
            f"La lluvia acumulada ({precip_acum_mm:.1f} mm) supera el umbral crítico "
            f"en {exceso:.1f} mm" if exceso > 0 else
            f"El score de riesgo es {score_pct}% (umbral crítico)"
        )
        evento_frag = (
            f", con {n_events_7d} evento(s) reportado(s) en los últimos 7 días" if n_events_7d > 0 else ""
        )
        return (
            f"{nombre} está en nivel CRÍTICO ({score_pct}%). {lluvia_frag}{evento_frag}. "
            f"La topografía de {terrain} agrava el riesgo de deslizamiento. "
            f"Activar protocolo de emergencia, evaluar evacuación inmediata y notificar al DAGRD."
        )

    if cat == "alto":
        lluvia_frag = (
            f"La lluvia acumulada ({precip_acum_mm:.1f} mm) supera el umbral operativo en {exceso:.1f} mm"
            if exceso > 0 else
            f"El modelo estima {score_pct}% de probabilidad de evento"
        )
        evento_frag = (
            f", sumado a {n_events_7d} evento(s) reciente(s)" if n_events_7d > 0 else ""
        )
        return (
            f"{nombre} alcanza nivel ALTO de riesgo ({score_pct}%). {lluvia_frag}{evento_frag}. "
            f"Se trata de una zona de {terrain} con historial de deslizamientos. "
            f"Realizar inspección de campo hoy e informar al comité local de gestión del riesgo."
        )

    if cat == "medio":
        lluvia_frag = (
            f"La lluvia acumulada ({precip_acum_mm:.1f} mm) se aproxima al umbral de alerta ({threshold_mm} mm)"
            if precip_acum_mm > threshold_mm * 0.6 else
            f"El modelo estima {score_pct}% de probabilidad de evento en 7 días"
        )
        return (
            f"{nombre} muestra nivel MEDIO de riesgo ({score_pct}%). {lluvia_frag}. "
            f"Monitorear evolución de precipitaciones en las próximas 24 horas. "
            f"Revisar canales de drenaje y mantener informada a la comunidad."
        )

    # bajo
    return (
        f"{nombre} presenta nivel BAJO de riesgo ({score_pct}%). "
        f"Las condiciones actuales (lluvia: {precip_acum_mm:.1f} mm, "
        f"umbral: {threshold_mm} mm) no superan los límites de alerta. "
        f"Continuar monitoreo rutinario."
    )

# ── OpenRouter client ──────────────────────────────────────────────────────────

async def _call_openrouter(
    commune_id: str,
    human_msg: str,
    db: AsyncSession,
    api_key: str,
) -> str | None:
    """Llama a GPT-4 Mini con tool use. Maneja hasta 1 ronda de tool calls."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://teyva.co",
        "X-Title": "TEYVA Risk Analysis",
    }
    messages: list[dict] = [{"role": "user", "content": human_msg}]
    payload: dict[str, Any] = {
        "model": _MODEL,
        "messages": messages,
        "system": _SYSTEM_PROMPT,
        "tools": _TOOLS,
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 200,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_OPENROUTER_BASE}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})

    # — Tool calls: ejecutar y hacer segunda llamada —
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            result = await _dispatch_tool(fn.get("name", ""), args, commune_id, db)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            })

        payload["messages"] = messages
        payload.pop("tools", None)        # segunda vuelta sin tools → respuesta final
        payload.pop("tool_choice", None)

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{_OPENROUTER_BASE}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()

        msg = data.get("choices", [{}])[0].get("message", {})

    return (msg.get("content") or "").strip() or None

# ── Public API ─────────────────────────────────────────────────────────────────

async def generate_risk_explanation(
    commune_id: str,
    risk_score: float,
    risk_category: str,
    precip_acum_mm: float,
    threshold_mm: float,
    n_events_7d: int,
    db: AsyncSession,
) -> tuple[str, str]:
    """
    Retorna (explanation_text, generated_by).
    generated_by es 'template' o el model id de OpenRouter.
    """
    nombre = _NOMBRES.get(commune_id, f"Comuna {commune_id}")
    is_ladera = _IS_LADERA.get(commune_id, False)

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if not api_key:
        # Sin API key → template determinístico
        text = _template_explanation(
            commune_id, nombre, risk_score, risk_category,
            precip_acum_mm, threshold_mm, n_events_7d, is_ladera,
        )
        return text, "template"

    # Con API key → GPT-4 Mini + tool use
    exceso_pct = round((precip_acum_mm - threshold_mm) / max(threshold_mm, 1) * 100, 1)
    human_msg = (
        f"DATOS DE {nombre.upper()} (ID: {commune_id}):\n"
        f"- Risk score: {risk_score:.4f} → categoría: {risk_category}\n"
        f"- Lluvia acumulada 24h: {precip_acum_mm:.1f} mm (umbral: {threshold_mm} mm, "
        f"exceso: {exceso_pct:+.1f}%)\n"
        f"- Eventos DAGRD últimos 7 días: {n_events_7d}\n"
        f"- Zona ladera: {'Sí' if is_ladera else 'No'}\n\n"
        f"Llama a las tools disponibles para enriquecer el análisis, luego genera la explicación."
    )

    try:
        text = await _call_openrouter(commune_id, human_msg, db, api_key)
        if text:
            return text, _MODEL
        # Fallback si respuesta vacía
        logger.warning("OpenRouter devolvió respuesta vacía para commune %s", commune_id)
    except Exception as exc:
        logger.warning("OpenRouter error para commune %s: %s — usando template", commune_id, exc)

    # Fallback siempre disponible
    text = _template_explanation(
        commune_id, nombre, risk_score, risk_category,
        precip_acum_mm, threshold_mm, n_events_7d, is_ladera,
    )
    return text, "template"
