from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from typing import Any

import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession

from agent.memory import get_history, save_turn
from agent.prompts import SYSTEM_PROMPT
from agent.tools import (
    compare_comunas,
    commune_display_name,
    find_communes_in_text,
    get_alert_status,
    get_historical_events,
    get_risk_by_comuna,
    get_top_risk_comunas,
)

_key = os.getenv("GEMINI_API_KEY")
if _key:
    genai.configure(api_key=_key)

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    generation_config={"temperature": 0.3, "max_output_tokens": 1024},
    system_instruction=SYSTEM_PROMPT,
)


def _norm_msg(message: str) -> str:
    nkfd = unicodedata.normalize("NFD", message.lower())
    return "".join(c for c in nkfd if unicodedata.category(c) != "Mn")


async def _build_tool_context(message: str, db: AsyncSession) -> str:
    mnorm = _norm_msg(message)
    communes = find_communes_in_text(message)
    chunks: list[str] = []

    compare_hit = bool(
        re.search(r"\b(compar|versus|vs\.?|frente a|respecto a)\b", mnorm)
        or re.search(r"\bentre\b.+\by\b", mnorm)
    )
    if compare_hit and len(communes) >= 2:
        tab = await compare_comunas(communes[:6], db)
        chunks.append(
            "Comparativa de comunas (última predicción ML por comuna):\n"
            + json.dumps(tab, ensure_ascii=False, default=str)
        )
        risk_ids: set[str] = set()
    else:
        risk_ids = set(communes)

    top_hit = any(
        p in mnorm
        for p in (
            "mas riesgo",
            "mayor riesgo",
            "top riesgo",
            "comuna con mas",
            "donde hay mas",
            "quien tiene mas",
            "peor riesgo",
            "mas peligro",
            "mas vulnerable",
        )
    ) or ("mas" in mnorm and "riesgo" in mnorm and "comuna" in mnorm)

    if top_hit:
        top = await get_top_risk_comunas(5, db)
        chunks.append(
            "Top comunas por risk_score (última predicción por comuna):\n"
            + json.dumps(top, ensure_ascii=False, default=str)
        )

    alert_hit = any(p in mnorm for p in ("alerta", "alertas", "en alerta", "riesgo critico"))
    if alert_hit and not compare_hit:
        alerts = await get_alert_status(db)
        chunks.append(
            "Comunas con categoría ALTO o CRÍTICO (última predicción en risk_predictions):\n"
            + json.dumps(alerts, ensure_ascii=False, default=str)
        )

    history_hit = any(
        p in mnorm
        for p in (
            "paso",
            "sucedio",
            "historial",
            "eventos",
            "emergencias",
            "hubo",
            "ultimo mes",
            "ultimos dias",
            "ultimas semanas",
        )
    )
    if history_hit and communes:
        days_back: int | None = None
        if "mes" in mnorm or "30 dias" in mnorm:
            days_back = 30
        elif "semana" in mnorm:
            days_back = 7
        cid = communes[0]
        ev = await get_historical_events(cid, db, limit=15, days_back=days_back)
        chunks.append(
            f"Eventos en landslide_events (comuna {commune_display_name(cid)}):\n"
            + json.dumps(ev, ensure_ascii=False, default=str)
        )

    if not compare_hit:
        for cid in list(risk_ids)[:3]:
            r = await get_risk_by_comuna(cid, db)
            chunks.append(
                f"Predicción actual ({commune_display_name(cid)}):\n" + json.dumps(r, ensure_ascii=False, default=str)
            )

    if not chunks:
        top = await get_top_risk_comunas(3, db)
        chunks.append(
            "Contexto mínimo (sin coincidencias claras de intención): top-3 riesgo actual\n"
            + json.dumps(top, ensure_ascii=False, default=str)
        )

    return "\n\n---\n\n".join(chunks)


def _contents_for_model(history: list[dict[str, str]], augmented_user_message: str) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for h in history:
        if h["role"] == "user":
            contents.append({"role": "user", "parts": [h["content"]]})
        elif h["role"] == "assistant":
            contents.append({"role": "model", "parts": [h["content"]]})
    contents.append({"role": "user", "parts": [augmented_user_message]})
    return contents


def _extract_reply(response: Any) -> str:
    try:
        text = response.text
        if text:
            return text.strip()
    except (ValueError, AttributeError):
        pass
    try:
        parts = response.candidates[0].content.parts
        return "".join(getattr(p, "text", "") for p in parts).strip()
    except (AttributeError, IndexError, KeyError):
        return "No pude obtener una respuesta del modelo. Intenta de nuevo en unos segundos."


async def chat(message: str, session_id: str, db: AsyncSession) -> str:
    if not os.getenv("GEMINI_API_KEY"):
        return (
            "TEYVA no puede consultar el modelo: falta la variable de entorno GEMINI_API_KEY. "
            "Configúrala en backend/.env según AGENTS.MD."
        )

    history = await get_history(session_id, db, limit=10)
    await save_turn(session_id, "user", message, db)

    tool_blob = await _build_tool_context(message, db)
    augmented = (
        "[Consulta automática a la base de datos TEYVA — usa solo estos hechos; si faltan datos, dilo]\n"
        f"{tool_blob}\n\n"
        f"[Pregunta del usuario]\n{message}"
    )

    contents = _contents_for_model(history, augmented)

    def _call_model() -> Any:
        return model.generate_content(contents)

    try:
        response = await asyncio.wait_for(asyncio.to_thread(_call_model), timeout=90.0)
        reply = _extract_reply(response)
    except asyncio.TimeoutError:
        reply = (
            "TEYVA: la respuesta del modelo tardó demasiado. Intenta de nuevo con una pregunta más corta "
            "o verifica tu conexión. Si el problema continúa, revisa GEMINI_API_KEY y cuotas del API."
        )
    except Exception as e:
        reply = (
            "TEYVA: no pude completar la consulta al modelo en este momento ("
            f"{type(e).__name__}). Verifica GEMINI_API_KEY y vuelve a intentar."
        )

    await save_turn(session_id, "assistant", reply, db)
    return reply
