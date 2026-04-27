from __future__ import annotations

import asyncio
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.memory import get_history, save_turn
from agent.prompts import SYSTEM_PROMPT
from agent.tools import (
    commune_display_name,
    find_communes_in_text,
    get_risk_by_comuna,
    get_top_risk_comunas,
)
from db.models import LandslideEvent, MLFeature, RiskPrediction

# Cargar backend/.env explícitamente para evitar depender del cwd del proceso.
_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_BACKEND_ENV, override=True)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def _safe_num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _risk_level_from_score(score: Any) -> str:
    value = _safe_num(score)
    if value is None:
        return "riesgo sin información reciente"
    if value > 0.8:
        return "riesgo crítico"
    if value > 0.6:
        return "riesgo alto"
    if value > 0.3:
        return "riesgo medio"
    return "riesgo bajo"


def _humanize_updated_at(created_at: Any) -> str:
    if not created_at:
        return "sin hora de actualización disponible"
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return "con actualización reciente"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    mins = max(1, int(delta.total_seconds() // 60))
    if mins < 60:
        return f"última actualización hace {mins} minutos"
    hours = mins // 60
    if hours < 24:
        return f"última actualización hace {hours} horas"
    days = hours // 24
    return f"última actualización hace {days} días"


def _natural_db_context_row(row: dict[str, Any] | None) -> str:
    if not row:
        return "No hay datos recientes para la comuna consultada."
    nombre = row.get("nombre") or row.get("commune_id") or "la comuna consultada"
    risk_text = _risk_level_from_score(row.get("risk_score"))
    updated_text = _humanize_updated_at(row.get("created_at"))
    return f"Comuna {nombre}: {risk_text}, {updated_text}."


def _natural_db_context_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No hay datos recientes para construir contexto territorial."
    return " ".join(_natural_db_context_row(r) for r in rows)


def _should_add_emergency_line(text: str) -> bool:
    tnorm = _norm_msg(text)
    return "riesgo alto" in tnorm or "riesgo critico" in tnorm or "riesgo crítico" in tnorm


def _append_emergency_line_if_needed(text: str) -> str:
    if not _should_add_emergency_line(text):
        return text
    emergency = "Si hay emergencia: DAGRD 4444444 · Bomberos 119 · Cruz Roja 132"
    if emergency in text:
        return text
    return f"{text}\n\n{emergency}"


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _load_prompt_context(db: AsyncSession) -> str:
    predictions_stmt = (
        select(
            RiskPrediction.commune_id,
            RiskPrediction.risk_category,
            RiskPrediction.risk_score,
            RiskPrediction.created_at,
        )
        .order_by(RiskPrediction.risk_score.desc())
    )
    predictions_rows = (await db.execute(predictions_stmt)).all()
    predictions_text = (
        "\n".join(
            f"- Comuna {commune_display_name(str(r.commune_id))} ({r.commune_id}): "
            f"riesgo {r.risk_category or 'Sin datos'} "
            f"(score={r.risk_score if r.risk_score is not None else 'Sin datos'}), "
            f"predicho en {_as_iso(r.created_at) or 'Sin datos'}"
            for r in predictions_rows
        )
        or "- Sin datos"
    )

    events_stmt = (
        select(LandslideEvent.commune_id, LandslideEvent.fecha, LandslideEvent.tipo_emergencia)
        .order_by(desc(LandslideEvent.fecha))
        .limit(20)
    )
    events_rows = (await db.execute(events_stmt)).all()
    events_text = (
        "\n".join(
            f"- Comuna {r.commune_id or 'Sin datos'}: fecha {r.fecha or 'Sin datos'}, "
            f"tipo {r.tipo_emergencia or 'Sin datos'}"
            for r in events_rows
        )
        or "- Sin datos"
    )

    rain_stmt = (
        select(MLFeature.commune_id, MLFeature.reference_date, MLFeature.features)
        .order_by(MLFeature.reference_date.desc())
        .limit(50)
    )
    rain_rows = (await db.execute(rain_stmt)).all()
    rain_text = (
        "\n".join(
            f"- Comuna {r.commune_id}: fecha {_as_iso(r.reference_date) or 'Sin datos'}, "
            f"lluvia diaria {((r.features or {}).get('precip_sum_mm_day') if isinstance(r.features, dict) else None) or 'Sin datos'} mm"
            for r in rain_rows
        )
        or "- Sin datos"
    )

    alerts_stmt = (
        select(
            RiskPrediction.commune_id,
            RiskPrediction.risk_category,
            RiskPrediction.risk_score,
            RiskPrediction.created_at,
        )
        .where(func.lower(RiskPrediction.risk_category).in_(["alto", "crítico", "critico"]))
        .order_by(RiskPrediction.risk_score.desc())
    )
    alert_rows = (await db.execute(alerts_stmt)).all()
    alerts_text = (
        "\n".join(
            f"- Comuna {commune_display_name(str(r.commune_id))} ({r.commune_id}): "
            f"{r.risk_category or 'Sin datos'} "
            f"(score={r.risk_score if r.risk_score is not None else 'Sin datos'}) "
            f"@ {_as_iso(r.created_at) or 'Sin datos'}"
            for r in alert_rows
        )
        or "- Sin datos"
    )

    return (
        "DATOS REALES PARA RESPONDER:\n"
        "Predicciones actuales por comuna:\n"
        f"{predictions_text}\n\n"
        "Últimos eventos de deslizamiento:\n"
        f"{events_text}\n\n"
        "Lluvia reciente por comuna:\n"
        f"{rain_text}\n\n"
        "Alertas activas (alto/crítico):\n"
        f"{alerts_text}"
    )


def _norm_msg(message: str) -> str:
    nkfd = unicodedata.normalize("NFD", message.lower())
    return "".join(c for c in nkfd if unicodedata.category(c) != "Mn")


async def _ask_ollama(system_text: str, user_text: str) -> str:
    url = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(url, json=payload)
    res.raise_for_status()
    return (res.json().get("message") or {}).get("content") or "Servicio no disponible"


async def chat(message: str, session_id: str, db: AsyncSession) -> str:
    history = await get_history(session_id, db, limit=6)
    await save_turn(session_id, "user", message, db)

    try:
        communes = find_communes_in_text(message)
        context_parts: list[str] = []
        if communes:
            row = await get_risk_by_comuna(communes[0], db)
            context_parts.append("Consulta puntual por comuna.")
            context_parts.append(_natural_db_context_row(row))
        else:
            top = await get_top_risk_comunas(3, db)
            if not top:
                context_parts.append(
                    "No hay predicciones recientes en risk_predictions; responder de forma preventiva y educativa."
                )
            else:
                context_parts.append("Consulta general sin comuna explícita.")
                context_parts.append(_natural_db_context_rows(top))

        if history:
            last_turns = history[-3:]
            context_parts.append(
                "Contexto breve de conversación previa: "
                + " | ".join(f"{t.get('role')}: {t.get('content')}" for t in last_turns)
            )

        global_data_context = await _load_prompt_context(db)
        local_context = "\n".join(p for p in context_parts if p.strip()) or "Sin datos recientes disponibles."
        data_context = f"{global_data_context}\n\nCONTEXTO DE LA PREGUNTA ACTUAL:\n{local_context}"
        system_with_context = f"{SYSTEM_PROMPT}\n\nCONTEXTO ACTUAL:\n{data_context}"
        reply = await _ask_ollama(system_with_context, message)
    except asyncio.TimeoutError:
        reply = "Servicio no disponible"
    except Exception as e:
        print(f"OLLAMA ERROR: {type(e).__name__}: {e}")
        reply = "Servicio no disponible"

    reply = _append_emergency_line_if_needed(reply)
    await save_turn(session_id, "assistant", reply, db)
    return reply
