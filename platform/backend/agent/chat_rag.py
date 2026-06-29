"""
Chat RAG — Loop de tool-calling con Ollama (local).

Reemplaza el chat de respuesta-única por un agente que decide qué herramientas
usar (RAG en ChromaDB + consultas a PostgreSQL) antes de responder.

Arquitectura:
    usuario → Ollama (llama3.2) ──decide──> tools (rag_tools.call_tool)
                  ↑                              │
                  └────── resultados ────────────┘   (máx 3 rondas)
                  ↓
              respuesta final

Las mismas tools (agent/rag_tools.py) las consumirá luego el servidor FastMCP
para que GPT-4o-mini vía OpenRouter acceda a ellas. Aquí se usan directamente
para testear todo localmente sin depender de OpenRouter.

Si Ollama falla o el modelo no soporta tools, hace fallback al chat clásico
(agent/chat.py) para no romper el endpoint.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from agent.memory import get_history, save_turn
from agent.prompts import SYSTEM_PROMPT
from agent.rag_tools import TOOL_SCHEMAS, call_tool, get_sources, reset_sources

_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_BACKEND_ENV, override=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
RAG_CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2"))
MAX_TOOL_ROUNDS = int(os.getenv("RAG_MAX_TOOL_ROUNDS", "3"))

# Instrucciones extra para que el modelo use las tools correctamente.
_RAG_SYSTEM_SUFFIX = """
TIENES HERRAMIENTAS para consultar datos reales. ÚSALAS antes de responder:
- search_knowledge: contexto histórico, geología de zonas, reportes de lluvia, eventos pasados.
- get_risk_predictions: riesgo actual de una comuna (modelo ML).
- get_recent_events: eventos/emergencias recientes.
- get_rainfall_timeseries: lluvia acumulada reciente de una comuna.
- get_scraper_health: estado de las fuentes de datos.

REGLAS (CRÍTICAS):
- Si la pregunta es sobre datos (riesgo, lluvia, eventos, una zona/comuna), LLAMA primero a la herramienta adecuada.
- Puedes combinar varias herramientas (ej. riesgo actual + contexto histórico).
- Usa EXCLUSIVAMENTE los datos que devuelvan las herramientas. NO inventes cifras, fechas ni municipios.
- Cada resultado trae su zona/municipio entre corchetes (ej. "[Zona: Villatina | Municipio: Medellín]").
  Atribuye cada dato a SU zona; no mezcles datos de zonas distintas ni cambies el municipio.
- Si la herramienta no trae datos, dilo con honestidad; NO rellenes con suposiciones.
- NUNCA escribas el nombre de una herramienta (search_knowledge, get_risk_predictions…) en tu respuesta al usuario.
""".strip()


def _build_system_prompt() -> str:
    return f"{SYSTEM_PROMPT}\n\n{_RAG_SYSTEM_SUFFIX}"


async def _ollama_chat(messages: list[dict], use_tools: bool = True) -> dict:
    """Una llamada a /api/chat de Ollama. Devuelve el objeto 'message'."""
    payload: dict[str, Any] = {
        "model": RAG_CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 400},
    }
    if use_tools:
        payload["tools"] = TOOL_SCHEMAS

    timeout = httpx.Timeout(360.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
    res.raise_for_status()
    return res.json().get("message") or {}


def _extract_tool_calls(message: dict) -> list[dict]:
    """Normaliza los tool_calls del mensaje de Ollama."""
    calls = message.get("tool_calls") or []
    out = []
    for c in calls:
        fn = c.get("function") or {}
        name = fn.get("name")
        args = fn.get("arguments")
        if name:
            out.append({"name": name, "arguments": args})
    return out


async def chat_rag(message: str, session_id: str, db: AsyncSession) -> str:
    """Entry point del chat con RAG + tools. Hace fallback al chat clásico si falla."""
    history = await get_history(session_id, db, limit=6)
    await save_turn(session_id, "user", message, db)

    reset_sources()  # colector de fuentes para este request

    messages: list[dict] = [{"role": "system", "content": _build_system_prompt()}]
    for turn in history:
        role = turn.get("role")
        if role in ("user", "assistant") and turn.get("content"):
            messages.append({"role": role, "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    try:
        reply = await _run_tool_loop(messages)
    except Exception as e:  # noqa: BLE001
        print(f"CHAT_RAG error ({type(e).__name__}): {e} — fallback a chat clásico")
        from agent.chat import chat as classic_chat

        # El chat clásico vuelve a guardar el turno del usuario; para evitar
        # duplicado usamos su propio flujo con un session_id efímero de respuesta.
        return await classic_chat(message, session_id, db)

    reply = _append_sources_footer(reply)
    reply = _append_emergency_line_if_needed(reply)
    await save_turn(session_id, "assistant", reply, db)
    return reply


def _append_sources_footer(text: str) -> str:
    """Anexa un bloque con las fuentes del RAG realmente consultadas."""
    sources = get_sources()
    if not sources:
        return text
    listado = "\n".join(f"• {s}" for s in sources)
    return f"{text}\n\n📚 Fuentes consultadas:\n{listado}"


async def _run_tool_loop(messages: list[dict]) -> str:
    """Ejecuta el ciclo modelo→tools→modelo hasta MAX_TOOL_ROUNDS."""
    for round_num in range(MAX_TOOL_ROUNDS):
        message = await _ollama_chat(messages, use_tools=True)
        tool_calls = _extract_tool_calls(message)

        if not tool_calls:
            content = (message.get("content") or "").strip()
            if content:
                return content
            # Sin contenido y sin tools → reintenta sin tools para forzar respuesta.
            break

        # Añade el turno del asistente (con sus tool_calls) y ejecuta cada tool.
        messages.append(message)
        for tc in tool_calls:
            result = await call_tool(tc["name"], tc["arguments"])
            print(f"  [tool] {tc['name']}({tc['arguments']}) → {result[:80]}...")
            messages.append({
                "role": "tool",
                "tool_name": tc["name"],
                "content": result,
            })

    # Última pasada sin tools para que sintetice una respuesta final.
    final = await _ollama_chat(messages, use_tools=False)
    return (final.get("content") or "No pude generar una respuesta con los datos disponibles.").strip()


# --- Reutiliza la línea de emergencia del chat clásico ---
def _append_emergency_line_if_needed(text: str) -> str:
    from agent.chat import _append_emergency_line_if_needed as _impl

    return _impl(text)
