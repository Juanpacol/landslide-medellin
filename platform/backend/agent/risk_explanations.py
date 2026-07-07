"""
Risk Explanation Service

Generates natural-language explanations for commune risk scores.

Behavior:
  - ANTHROPIC_API_KEY set  → calls Claude (Anthropic) with tool use + salida
    JSON estructurada (`output_config.format`, garantiza que cumpla el schema)
  - ANTHROPIC_API_KEY unset → builds a deterministic template explanation
    (honest, data-driven, zero hallucinations possible)

Prompt engineering techniques used:
  - Role priming + negative constraints ("NUNCA inventes")
  - Tool-use grounding (model must call tools before answering)
  - Low temperature (0.3) for consistency
  - Strict token budget (max_tokens=400)
  - Structured human message with all numeric context explicit
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import RISK_THRESHOLD_ALTO, RISK_THRESHOLD_CRITICO, RISK_THRESHOLD_MEDIO
from db.models.ml_feature import MLFeature
from db.models.risk_prediction import RiskPrediction

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
def _get_anthropic_client():
    from infrastructure.external.llm_client import get_anthropic_client

    return get_anthropic_client()

from domain.communes import COMMUNES as _COMMUNES

_NOMBRES: dict[str, str] = {c.id: c.nombre for c in _COMMUNES} | {
    c.official_code: c.nombre for c in _COMMUNES
}

_IS_LADERA: dict[str, bool] = {
    "1": True, "2": True, "3": True, "4": False, "5": False,
    "6": True, "7": True, "8": True, "9": True, "10": False,
    "11": False, "12": False, "13": True, "14": False, "15": False,
    "16": True, "50": True, "60": True, "70": True, "80": False, "90": True,
}

# ── Structured output schema (JSON mode, OpenAI-compatible) ────────────────────

_EXPLANATION_SCHEMA_HINT = """
Responde ÚNICAMENTE con un objeto JSON (sin markdown, sin texto fuera del JSON) con esta forma exacta:
{
  "title": "string — una frase (máx 12 palabras) resumiendo la situación",
  "factors": ["string", "..."],  // 1 a 3 factores concretos, cada uno una frase corta con datos reales
  "urgency": "bajo" | "medio" | "alto" | "critico",
  "recommended_action": "string — una acción concreta para el operario"
}
"""

# ── System prompt (applied once, high token efficiency) ────────────────────────

_SYSTEM_PROMPT = """TAREA: Genera un análisis estructurado (JSON) sobre POR QUÉ una comuna
de Medellín tiene su nivel de riesgo de deslizamiento actual, listo
para que un operario de campo actúe de inmediato.

ERES: experto en análisis de riesgo de deslizamientos del sistema TEYVA.

REGLAS ESTRICTAS:
1. Usa SOLO los datos numéricos que el usuario te proporciona o que obtienes vía tools.
2. NUNCA inventes valores, eventos, fechas o predicciones no presentes en los datos.
3. Cada factor es una frase corta y concreta con datos reales (no más de 20 palabras).
4. Tono: técnico-operativo, directo. Urgente si categoría es "alto" o "critico".
5. NUNCA uses: "podría", "tal vez", "aparentemente", "posiblemente".
6. `recommended_action` siempre debe ser una acción concreta e inmediata para el operario (no "monitorear algo").

CATEGORÍAS:
- bajo (<0.35): Monitoreo rutinario.
- medio (0.35-0.65): Vigilancia activa.
- alto (0.65-0.90): Alerta operativa — inspección de campo.
- critico (≥0.90): Acción inmediata — evaluar evacuación.

EJEMPLOS DE SALIDAS IDEALES (uno por categoría):

EJEMPLO 1 — CATEGORÍA BAJO (precip 20mm, umbral 35mm, 0 eventos):
{
  "title": "Popular presenta nivel BAJO de riesgo (20.0%)",
  "factors": ["Lluvia acumulada: 20mm (umbral: 35mm) — no supera límites de alerta"],
  "urgency": "bajo",
  "recommended_action": "Continuar monitoreo rutinario."
}
Razón: Es conciso (no exagera), cita datos precisos, acción simple.

EJEMPLO 2 — CATEGORÍA MEDIO (precip 45mm, umbral 60mm, 2 eventos):
{
  "title": "Manrique muestra nivel MEDIO de riesgo (50.0%)",
  "factors": ["Lluvia acumulada 45mm se aproxima al umbral 60mm", "Monitorear evolución de precipitaciones en próximas 24 horas"],
  "urgency": "medio",
  "recommended_action": "Revisar canales de drenaje y mantener informada a la comunidad."
}
Razón: Cita el factor crítico (lluvia), proporciona threshold para comparar, acción proactiva.

EJEMPLO 3 — CATEGORÍA ALTO (precip 90mm, umbral 70mm, 5 eventos):
{
  "title": "Castilla alcanza nivel ALTO de riesgo (75.0%)",
  "factors": ["Lluvia acumulada 90mm supera umbral operativo en 20mm", "5 evento(s) reciente(s) reportado(s)"],
  "urgency": "alto",
  "recommended_action": "Realizar inspección de campo hoy e informar al comité local de gestión del riesgo."
}
Razón: Múltiples factores con datos concretos, acción inmediata y específica.

EJEMPLO 4 — CATEGORÍA CRÍTICO (precip 200mm, umbral 90mm, 15 eventos):
{
  "title": "Robledo en nivel CRÍTICO (95.0%)",
  "factors": ["Lluvia acumulada 200mm supera umbral crítico en 110mm", "15 evento(s) reportado(s) en 7 días", "Topografía de ladera agrava el riesgo"],
  "urgency": "critico",
  "recommended_action": "Activar protocolo de emergencia, evaluar evacuación inmediata y notificar al DAGRD."
}
Razón: Múltiples factores críticos, lenguaje urgente, acciones escaladas (evacuación).

CONTRA-EJEMPLO — NO HAGAS ESTO (vago, sin datos):
{
  "title": "Castilla podría tener riesgo",
  "factors": ["Tal vez hay mucha lluvia", "Podrían ocurrir eventos"],
  "urgency": "alto",
  "recommended_action": "Monitorear la situación"
}
Errores: vaguedad ("podría", "tal vez"), sin números, acción genérica.
""" + _EXPLANATION_SCHEMA_HINT

# ── Tool definitions (formato OpenAI; se convierten a formato Claude abajo) ────

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


def _openai_tools_to_claude(tools: list[dict]) -> list[dict]:
    """Convierte _TOOLS (formato OpenAI) a formato Claude — misma conversión
    que `chat_rag._openai_tools_to_claude`, duplicada aquí porque este es un
    catálogo de tools distinto (propio de explicaciones de riesgo)."""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


_CLAUDE_TOOLS = _openai_tools_to_claude(_TOOLS)

# JSON Schema real (no solo texto de instrucción) para forzar la forma exacta
# de la salida vía `output_config.format` de Claude — más confiable que pedirlo
# por prosa en el system prompt (que es lo único que puede hacer el template
# determinístico / lo que hacía OpenRouter con `response_format: json_object`,
# que solo garantiza JSON válido, no que cumpla este schema).
_EXPLANATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "factors": {"type": "array", "items": {"type": "string"}},
        "urgency": {"type": "string", "enum": ["bajo", "medio", "alto", "critico"]},
        "recommended_action": {"type": "string"},
    },
    "required": ["title", "factors", "urgency", "recommended_action"],
    "additionalProperties": False,
}

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

def _template_explanation_structured(
    commune_id: str,
    nombre: str,
    risk_score: float,
    risk_category: str,
    precip_acum_mm: float,
    threshold_mm: float,
    n_events_7d: int,
    is_ladera: bool,
) -> dict[str, Any]:
    """Genera explicación determinística estructurada basada en datos reales.

    Sin hallucinations: cada campo se arma con los mismos fragmentos que antes
    se concatenaban en un párrafo — ahora cada pieza va a su propio campo del
    schema (`title`, `factors`, `urgency`, `recommended_action`).
    """

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
        factors = [lluvia_frag]
        if n_events_7d > 0:
            factors.append(f"{n_events_7d} evento(s) reportado(s) en los últimos 7 días")
        factors.append(f"La topografía de {terrain} agrava el riesgo de deslizamiento")
        return {
            "title": f"{nombre} en nivel CRÍTICO ({score_pct}%)",
            "factors": factors,
            "urgency": "critico",
            "recommended_action": "Activar protocolo de emergencia, evaluar evacuación inmediata y notificar al DAGRD.",
        }

    if cat == "alto":
        lluvia_frag = (
            f"La lluvia acumulada ({precip_acum_mm:.1f} mm) supera el umbral operativo en {exceso:.1f} mm"
            if exceso > 0 else
            f"El modelo estima {score_pct}% de probabilidad de evento"
        )
        factors = [lluvia_frag]
        if n_events_7d > 0:
            factors.append(f"{n_events_7d} evento(s) reciente(s) reportado(s)")
        factors.append(f"Zona de {terrain} con historial de deslizamientos")
        return {
            "title": f"{nombre} alcanza nivel ALTO de riesgo ({score_pct}%)",
            "factors": factors,
            "urgency": "alto",
            "recommended_action": "Realizar inspección de campo hoy e informar al comité local de gestión del riesgo.",
        }

    if cat == "medio":
        lluvia_frag = (
            f"La lluvia acumulada ({precip_acum_mm:.1f} mm) se aproxima al umbral de alerta ({threshold_mm} mm)"
            if precip_acum_mm > threshold_mm * 0.6 else
            f"El modelo estima {score_pct}% de probabilidad de evento en 7 días"
        )
        return {
            "title": f"{nombre} muestra nivel MEDIO de riesgo ({score_pct}%)",
            "factors": [lluvia_frag, "Monitorear evolución de precipitaciones en las próximas 24 horas"],
            "urgency": "medio",
            "recommended_action": "Revisar canales de drenaje y mantener informada a la comunidad.",
        }

    # bajo
    return {
        "title": f"{nombre} presenta nivel BAJO de riesgo ({score_pct}%)",
        "factors": [
            f"Lluvia acumulada: {precip_acum_mm:.1f} mm (umbral: {threshold_mm} mm) — no supera los límites de alerta"
        ],
        "urgency": "bajo",
        "recommended_action": "Continuar monitoreo rutinario.",
    }


def _render_narrative(structured: dict[str, Any]) -> str:
    """Arma el párrafo humano de siempre a partir del dict estructurado.

    La usan tanto el camino template como el camino LLM, así el texto
    narrativo que ya consumen Slack/API/frontend no cambia de "voz", solo
    cambia su origen (ahora se deriva de la estructura, no al revés).
    """
    title = str(structured.get("title") or "").strip()
    factors = [str(f).strip() for f in (structured.get("factors") or []) if str(f).strip()]
    recommended_action = str(structured.get("recommended_action") or "").strip()

    parts = [p for p in [title, *factors, recommended_action] if p]
    narrative = ". ".join(p.rstrip(".") for p in parts)
    return f"{narrative}." if narrative else ""

# ── OpenRouter client ──────────────────────────────────────────────────────────

def _validate_structured(data: Any) -> dict[str, Any] | None:
    """Valida que el JSON parseado tenga las 4 claves esperadas y bien formadas.

    Si algo falta o tiene el tipo equivocado, se trata como fallo (se cae a
    template en el llamador) — cero campos nulos toleran salir de acá.
    """
    if not isinstance(data, dict):
        return None

    title = data.get("title")
    factors = data.get("factors")
    urgency = data.get("urgency")
    recommended_action = data.get("recommended_action")

    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(factors, list) or not factors:
        return None
    factors_clean = [str(f).strip() for f in factors if str(f).strip()]
    if not factors_clean:
        return None
    if not isinstance(urgency, str) or urgency.strip().lower() not in {"bajo", "medio", "alto", "critico"}:
        return None
    if not isinstance(recommended_action, str) or not recommended_action.strip():
        return None

    return {
        "title": title.strip(),
        "factors": factors_clean,
        "urgency": urgency.strip().lower(),
        "recommended_action": recommended_action.strip(),
    }


async def _call_anthropic(
    commune_id: str,
    human_msg: str,
    db: AsyncSession,
) -> str | None:
    """Llama a Claude con tool use. Maneja hasta 1 ronda de tool calls.

    A diferencia de OpenRouter/OpenAI (donde `response_format` no se puede
    combinar con `tools` en la misma llamada, por eso el código viejo hacía
    dos rondas con configuraciones distintas), Claude sí soporta `tools` +
    `output_config.format` juntos: el modelo puede decidir llamar una tool y,
    cuando ya no necesita más, su respuesta final llega garantizada conforme
    al JSON schema — sin depender de que respete la instrucción de prosa.
    """
    client = _get_anthropic_client()
    messages: list[dict] = [{"role": "user", "content": human_msg}]
    kwargs: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 400,
        "temperature": 0.3,
        "system": _SYSTEM_PROMPT,
        "tools": _CLAUDE_TOOLS,
        "output_config": {"format": {"type": "json_schema", "schema": _EXPLANATION_JSON_SCHEMA}},
    }

    response = await asyncio.to_thread(client.messages.create, messages=messages, **kwargs)

    tool_calls = [b for b in response.content if b.type == "tool_use"]
    if tool_calls:
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            result = await _dispatch_tool(tc.name, tc.input, commune_id, db)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
        messages.append({"role": "user", "content": tool_results})

        response = await asyncio.to_thread(client.messages.create, messages=messages, **kwargs)

    text = next((b.text for b in response.content if b.type == "text"), None)
    return text.strip() if text else None


async def _call_anthropic_structured(
    commune_id: str,
    human_msg: str,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """Llama a Claude y devuelve el dict estructurado ya validado, o None.

    None significa "no se pudo obtener una estructura confiable" — el
    llamador (`generate_risk_explanation`) debe caer al template determinístico
    en ese caso (mismo criterio de "cero alucinaciones toleradas" del resto
    del archivo).
    """
    raw = await _call_anthropic(commune_id, human_msg, db)
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Claude devolvió JSON inválido para commune %s: %s", commune_id, exc)
        return None

    structured = _validate_structured(parsed)
    if structured is None:
        logger.warning("Claude devolvió estructura incompleta para commune %s: %r", commune_id, parsed)
    return structured

# ── Public API ─────────────────────────────────────────────────────────────────

async def generate_risk_explanation(
    commune_id: str,
    risk_score: float,
    risk_category: str,
    precip_acum_mm: float,
    threshold_mm: float,
    n_events_7d: int,
    db: AsyncSession,
) -> tuple[str, str, dict[str, Any]]:
    """
    Retorna (explanation_text, generated_by, structured).
    generated_by es 'template' o el model id de Anthropic (ANTHROPIC_MODEL).
    structured es el dict {title, factors, urgency, recommended_action}
    del que `explanation_text` es derivado (vía `_render_narrative`).
    """
    nombre = _NOMBRES.get(commune_id, f"Comuna {commune_id}")
    is_ladera = _IS_LADERA.get(commune_id, False)

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    if not api_key:
        # Sin API key → template determinístico
        structured = _template_explanation_structured(
            commune_id, nombre, risk_score, risk_category,
            precip_acum_mm, threshold_mm, n_events_7d, is_ladera,
        )
        return _render_narrative(structured), "template", structured

    # Con API key → Claude + tool use
    exceso_pct = round((precip_acum_mm - threshold_mm) / max(threshold_mm, 1) * 100, 1)
    human_msg = (
        f"<commune_data>\n"
        f"<name>{nombre}</name>\n"
        f"<id>{commune_id}</id>\n"
        f"<risk_score>{risk_score:.4f}</risk_score>\n"
        f"<risk_category>{risk_category}</risk_category>\n"
        f"<precipitation_7d_mm>{precip_acum_mm:.1f}</precipitation_7d_mm>\n"
        f"<threshold_mm>{threshold_mm}</threshold_mm>\n"
        f"<precipitation_excess_pct>{exceso_pct:+.1f}</precipitation_excess_pct>\n"
        f"<events_7d>{n_events_7d}</events_7d>\n"
        f"<is_ladera>{'Sí' if is_ladera else 'No'}</is_ladera>\n"
        f"</commune_data>\n\n"
        f"<task>\n"
        f"Llama a las tools disponibles para enriquecer el análisis, luego genera la explicación estructurada.\n"
        f"</task>"
    )

    try:
        structured = await _call_anthropic_structured(commune_id, human_msg, db)
        if structured:
            return _render_narrative(structured), ANTHROPIC_MODEL, structured
        # Fallback si no se pudo obtener estructura confiable
        logger.warning("Claude no devolvió estructura válida para commune %s", commune_id)
    except Exception as exc:
        logger.warning("Claude error para commune %s: %s — usando template", commune_id, exc)

    # Fallback siempre disponible
    structured = _template_explanation_structured(
        commune_id, nombre, risk_score, risk_category,
        precip_acum_mm, threshold_mm, n_events_7d, is_ladera,
    )
    return _render_narrative(structured), "template", structured
