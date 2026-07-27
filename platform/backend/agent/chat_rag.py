"""
Chat RAG — Loop de tool-calling, con Claude (Anthropic) como proveedor
primario y Ollama (local) como fallback.

Reemplaza el chat de respuesta-única por un agente que decide qué herramientas
usar (RAG en ChromaDB + consultas a PostgreSQL) antes de responder.

Arquitectura (proveedor seleccionable vía LLM_PROVIDER):
    usuario → Claude o Ollama ──decide──> tools (rag_tools.call_tool)
                  ↑                              │
                  └────── resultados ────────────┘   (máx 3 rondas)
                  ↓
              respuesta final

`LLM_PROVIDER=anthropic` (default) usa la API de Claude; si falta
`ANTHROPIC_API_KEY` o la llamada falla, cae automáticamente a Ollama
(`LLM_PROVIDER=ollama` fuerza Ollama directamente, útil sin conexión).
Ambos caminos comparten el mismo `SYSTEM_PROMPT`, `_RAG_SYSTEM_SUFFIX` y las
mismas tools de `agent/rag_tools.py` — solo cambia el "cableado" del formato
de cada API (ver `_openai_tools_to_claude` para la conversión de esquemas).

Si ambos proveedores fallan, hace fallback al chat clásico (agent/chat.py)
para no romper el endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from agent.guardrails import PromptInjectionDetected, scan_output, validate_input
from agent.memory import get_history, save_turn
from agent.prompts import SYSTEM_PROMPT
from agent.rag_tools import TOOL_SCHEMAS, call_tool, get_sources, reset_sources, set_report_session

_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
# override=False: el entorno real (Docker/CI/prod) SIEMPRE gana sobre el
# archivo .env — con override=True un `API_TOKEN=` vacío en .env pisaba
# el token real exportado en producción.
load_dotenv(dotenv_path=_BACKEND_ENV, override=False)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
RAG_CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2"))
MAX_TOOL_ROUNDS = int(os.getenv("RAG_MAX_TOOL_ROUNDS", "3"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")


def _get_anthropic_client():
    from infrastructure.external.llm_client import get_anthropic_client

    return get_anthropic_client()


def _openai_tools_to_claude(tools: list[dict]) -> list[dict]:
    """Convierte TOOL_SCHEMAS (formato OpenAI/Ollama) al formato de Claude.

    Única fuente de verdad de las tools sigue siendo TOOL_SCHEMAS en
    rag_tools.py — esto solo traduce la forma del JSON, no la lógica.
    OpenAI: {"type": "function", "function": {name, description, parameters}}
    Claude: {name, description, input_schema}
    """
    claude_tools = []
    for t in tools:
        fn = t.get("function", {})
        claude_tools.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            }
        )
    return claude_tools


_CLAUDE_TOOLS = _openai_tools_to_claude(TOOL_SCHEMAS)

# Instrucciones extra para que el modelo use las tools correctamente.
_RAG_SYSTEM_SUFFIX = """
TAREA: Responde preguntas sobre riesgo de deslizamientos en comunas de
Medellín usando SIEMPRE las herramientas de datos reales de abajo —
nunca respondas de memoria cuando la pregunta involucra datos.

HERRAMIENTAS DISPONIBLES:
- search_knowledge: contexto histórico, geología de zonas, reportes de lluvia, eventos pasados.
- get_risk_predictions: riesgo actual de una comuna (modelo ML).
- get_recent_events: eventos/emergencias recientes.
- get_rainfall_timeseries: lluvia acumulada reciente de una comuna.
- get_scraper_health: estado de las fuentes de datos.
- report_incident: registra un reporte ciudadano de una situación de riesgo observada.
- get_situation_report: panorama completo del valle en lenguaje plano.
- get_evacuation_routes: zonas seguras candidatas y rutas caminando desde una comuna.

CUÁNDO USAR CADA UNA (ejemplos):
- "¿Riesgo en Villatina?" → get_risk_predictions + get_rainfall_timeseries (+ search_knowledge si piden contexto/por qué)
- "¿Qué pasó en Castilla?" / "¿Hubo emergencias?" → get_recent_events
- "¿Cuánta lluvia ha caído en Robledo?" → get_rainfall_timeseries
- "¿Están funcionando los sensores?" → get_scraper_health
- "Veo grietas en mi casa" / "quiero reportar algo" → pregunta comuna y qué observa, luego report_incident
- "Dame un resumen de la situación" / "¿cómo está todo hoy?" → get_situation_report
- "¿Adónde evacuo?" / "rutas seguras" / "dónde me refugio" → get_evacuation_routes

SOBRE REPORTES CIUDADANOS: si alguien describe una situación de peligro
inminente (deslizamiento activo, personas en riesgo), dile PRIMERO que llame
al DAGRD 4444444 o Bomberos 119, y además registra el reporte.

SI LA PREGUNTA ES DE TIPO "POR QUÉ" (por qué subió/bajó el riesgo, por qué
hay alerta, qué está pasando en una zona), sigue este proceso antes de
responder — no te quedes con el primer dato que encuentres:
1. Consulta get_risk_predictions para el score y categoría actuales.
2. Consulta get_rainfall_timeseries para ver si la lluvia acumulada subió.
3. Consulta get_recent_events para ver si hubo eventos/emergencias nuevos.
4. Compara los tres factores y determina cuál pesa más en la situación actual.
5. Responde citando el factor dominante primero; menciona los demás solo si son relevantes.
No expliques un cambio de riesgo con un solo factor si las herramientas muestran más de uno relevante.

REGLAS (CRÍTICAS):
- Si la pregunta es sobre datos (riesgo, lluvia, eventos, una zona/comuna), LLAMA primero a la herramienta adecuada.
- Puedes combinar varias herramientas (ej. riesgo actual + contexto histórico).
- Usa EXCLUSIVAMENTE los datos que devuelvan las herramientas. NO inventes cifras, fechas ni municipios.
- Cada resultado trae su zona/municipio entre corchetes (ej. "[Zona: Villatina | Municipio: Medellín]").
  Atribuye cada dato a SU zona; no mezcles datos de zonas distintas ni cambies el municipio.
- Si la herramienta no trae datos, dilo con honestidad; NO rellenes con suposiciones.
- NUNCA escribas el nombre de una herramienta (search_knowledge, get_risk_predictions…) en tu respuesta al usuario.

EJEMPLOS DE RESPUESTAS IDEALES (cómo debes sonar):

<example_1>
<input>¿Cuál es el riesgo en San Javier?</input>
<output>
San Javier está en riesgo alto. La lluvia acumulada en los últimos 7 días
es muy baja (0mm), pero el modelo estima una probabilidad alta de evento
(0.65). Esto indica saturación previa del terreno por lluvias anteriores.
Recomendación: alerta operativa — realizar inspección de campo hoy.
</output>
<explanation>
Este es un buen output porque:
- Menciona la comuna específica (San Javier)
- Cita datos concretos con números (0mm, 0.65)
- Explica por qué el riesgo es alto (saturación previa)
- Proporciona una acción específica e inmediata ("inspección de campo hoy")
- No usa lenguaje vago ("podría", "tal vez")
</explanation>
</example_1>

<example_2>
<input>¿Por qué subió el riesgo en Castilla?</input>
<output>
El riesgo en Castilla subió principalmente porque la lluvia acumulada
(90mm en 7 días) superó el umbral operativo (70mm) en 20mm, saturando
el terreno. Además, se reportaron 5 eventos de emergencia en la zona
en los últimos 7 días. Ambos factores indican condiciones críticas.
</output>
<explanation>
Este es un buen output porque:
- Responde directamente la pregunta "por qué"
- Cita el factor dominante primero (lluvia)
- Incluye datos específicos (90mm, 70mm, 5 eventos)
- Menciona factores adicionales si son relevantes
- Explica la implicación (condiciones críticas)
</explanation>
</example_2>

<example_3>
<input>¿Cuál es el riesgo en Buenos Aires?</input>
<output>
Buenos Aires está en riesgo bajo. La lluvia acumulada en 7 días es 8.5mm,
bien por debajo del umbral de 35mm. No hay eventos reportados en la zona.
Continúa con monitoreo rutinario.
</output>
<explanation>
Este es un buen output porque:
- Es conciso (no exagera si el riesgo es bajo)
- Incluye números concretos (8.5mm vs 35mm)
- Menciona ausencia de eventos (dato importante)
- Proporciona acción simple pero clara (monitoreo rutinario)
</explanation>
</example_3>

<example_4>
<input>¿Cuál es el riesgo en Villatina?</input>
<output>
No reconozco la comuna «Villatina» en los datos disponibles.
¿Te refieres a Villa Hermosa? Puedo ayudarte con riesgo en cualquiera
de las 19 comunas de Medellín. ¿De cuál quieres información?
</output>
<explanation>
Este es un buen output porque:
- Admite la limitación honestamente (no inventa datos)
- Sugiere una alternativa probable (Villa Hermosa)
- Ofrece ayuda (19 comunas disponibles)
- No intenta rellenar con suposiciones
</explanation>
</example_4>
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


async def _ollama_chat_stream(messages: list[dict]) -> AsyncIterator[str]:
    """Variante en streaming de `_ollama_chat()`, SIN tools (`stream: True`).

    Se usa exclusivamente para la ronda final de síntesis del loop de tools,
    cuando el modelo ya tiene los resultados de las herramientas en el
    historial de mensajes y solo debe redactar la respuesta en lenguaje
    natural — esa es la única parte del loop que puede transmitirse en vivo,
    porque las rondas de decisión de tools necesitan el JSON completo de
    `tool_calls` (no se pueden leer en streaming).
    """
    payload: dict[str, Any] = {
        "model": RAG_CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.3, "num_predict": 400},
    }
    timeout = httpx.Timeout(360.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as res:
            res.raise_for_status()
            async for line in res.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                text = (chunk.get("message") or {}).get("content", "")
                if text:
                    yield text
                if chunk.get("done"):
                    break


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


# ─────────────────────────────────────────────────────────────────────────
# Proveedor Claude (Anthropic) — mismo rol que las funciones _ollama_* de
# arriba, pero hablando el protocolo propio de la Messages API.
# ─────────────────────────────────────────────────────────────────────────


async def _anthropic_chat(messages: list[dict], system: str, use_tools: bool = True) -> Any:
    """Una llamada a Claude. Devuelve el objeto Message completo (se necesita
    `.content` para los bloques `tool_use` y poder reenviarlos tal cual)."""
    client = _get_anthropic_client()
    kwargs: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 500,
        "temperature": 0.3,
        "system": system,
        "messages": messages,
    }
    if use_tools:
        kwargs["tools"] = _CLAUDE_TOOLS
    return await asyncio.to_thread(client.messages.create, **kwargs)


async def _anthropic_chat_stream(messages: list[dict], system: str) -> AsyncIterator[str]:
    """Streaming de la síntesis final (sin tools), rol equivalente a
    `_ollama_chat_stream()`. El SDK de Anthropic transmite de forma síncrona
    (`client.messages.stream()` es un context manager sync), así que se
    corre en un hilo aparte y se puentea a un async generator vía una cola:
    cada chunk de texto se empuja con `call_soon_threadsafe` para no bloquear
    el event loop mientras el hilo productor sigue leyendo el stream de red.
    """
    import threading

    client = _get_anthropic_client()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _produce() -> None:
        try:
            with client.messages.stream(
                model=ANTHROPIC_MODEL,
                max_tokens=500,
                temperature=0.3,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as exc:  # noqa: BLE001
            print(f"  [anthropic stream error] {type(exc).__name__}: {exc}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_produce, daemon=True).start()

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


def _extract_claude_tool_calls(response: Any) -> list[dict]:
    """Extrae los bloques `tool_use` de una respuesta de Claude."""
    return [
        {"id": block.id, "name": block.name, "arguments": block.input}
        for block in response.content
        if block.type == "tool_use"
    ]


def _extract_claude_text(response: Any) -> str:
    """Concatena los bloques de texto de una respuesta de Claude."""
    return "".join(block.text for block in response.content if block.type == "text").strip()


async def _run_tool_loop_claude(system: str, messages: list[dict]) -> str:
    """Equivalente a `_run_tool_loop()` pero para el round-trip de Claude:
    el turno del asistente se reenvía tal cual (incluye sus bloques
    `tool_use`), y los resultados van en un mensaje `user` con bloques
    `tool_result` — no como mensajes `role: "tool"` (eso es formato Ollama).
    """
    for _round_num in range(MAX_TOOL_ROUNDS):
        response = await _anthropic_chat(messages, system, use_tools=True)
        tool_calls = _extract_claude_tool_calls(response)

        if not tool_calls:
            content = _extract_claude_text(response)
            if content:
                return content
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            result = await call_tool(tc["name"], tc["arguments"])
            print(f"  [tool] {tc['name']}({tc['arguments']}) → {result[:80]}...")
            tool_results.append({"type": "tool_result", "tool_use_id": tc["id"], "content": result})
        messages.append({"role": "user", "content": tool_results})

    final = await _anthropic_chat(messages, system, use_tools=False)
    return _extract_claude_text(final) or "No pude generar una respuesta con los datos disponibles."


async def _run_tool_loop_claude_stream(system: str, messages: list[dict]) -> AsyncIterator[str]:
    """Variante en streaming de `_run_tool_loop_claude()` — mismo criterio que
    `_run_tool_loop_stream()`: las rondas de decisión de tools no se
    transmiten (necesitan el JSON completo de `tool_use`), solo la síntesis
    final."""
    for _round_num in range(MAX_TOOL_ROUNDS):
        response = await _anthropic_chat(messages, system, use_tools=True)
        tool_calls = _extract_claude_tool_calls(response)

        if not tool_calls:
            # Sin más tools que llamar: la síntesis final se transmite de
            # verdad más abajo. No reusamos el texto de esta llamada
            # no-streamed — eso mostraría la respuesta completa de golpe
            # en vez de palabra por palabra.
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            result = await call_tool(tc["name"], tc["arguments"])
            print(f"  [tool] {tc['name']}({tc['arguments']}) → {result[:80]}...")
            tool_results.append({"type": "tool_result", "tool_use_id": tc["id"], "content": result})
        messages.append({"role": "user", "content": tool_results})

    got_any = False
    async for piece in _anthropic_chat_stream(messages, system):
        got_any = True
        yield piece
    if not got_any:
        yield "No pude generar una respuesta con los datos disponibles."


async def _generate_reply(system: str, conversation: list[dict]) -> str:
    """Genera la respuesta con el proveedor configurado (`LLM_PROVIDER`,
    default 'anthropic'), con fallback automático a Ollama si Claude falla
    (falta `ANTHROPIC_API_KEY`, error de red, rate limit, etc.)."""
    if LLM_PROVIDER == "anthropic":
        try:
            return await _run_tool_loop_claude(system, list(conversation))
        except Exception as exc:  # noqa: BLE001
            print(f"CHAT_RAG anthropic error ({type(exc).__name__}): {exc} — fallback a Ollama")

    ollama_messages = [{"role": "system", "content": system}, *conversation]
    return await _run_tool_loop(ollama_messages)


async def _generate_reply_stream(system: str, conversation: list[dict]) -> AsyncIterator[str]:
    """Variante en streaming de `_generate_reply()`.

    Mismo trade-off ya aceptado en `chat.py` (ver `chat_stream`): si Claude
    falla A MITAD del stream (después de emitir texto), el fallback a Ollama
    sigue agregando texto nuevo sin poder "deshacer" lo ya emitido — no se
    puede retractar contenido que ya salió por SSE. Solo importa evitarlo
    cuando la falla ocurre ANTES de emitir nada, que es el caso común
    (key ausente, conexión rechazada).
    """
    if LLM_PROVIDER == "anthropic":
        try:
            async for piece in _run_tool_loop_claude_stream(system, list(conversation)):
                yield piece
            return
        except Exception as exc:  # noqa: BLE001
            print(
                f"CHAT_RAG_STREAM anthropic error ({type(exc).__name__}): {exc} — fallback a Ollama"
            )

    ollama_messages = [{"role": "system", "content": system}, *conversation]
    async for piece in _run_tool_loop_stream(ollama_messages):
        yield piece


async def chat_rag(message: str, session_id: str, db: AsyncSession) -> str:
    """Entry point del chat con RAG + tools. Hace fallback al chat clásico si falla."""
    history = await get_history(session_id, db, limit=6)
    await save_turn(session_id, "user", message, db)

    # Se atrapa AQUÍ, no se deja burbujear al manejador global 422: el chat
    # debe mantener su contrato estable (200 con ChatResponse), un 422
    # rompería la UX. Se guarda el turno del asistente con el rechazo, así
    # queda trazado en el historial que hubo un intento.
    try:
        message = validate_input(message)
    except PromptInjectionDetected as exc:
        reply = str(exc)
        await save_turn(session_id, "assistant", reply, db)
        return reply

    reset_sources()  # colector de fuentes para este request
    set_report_session(session_id)  # para la tool report_incident

    system = _build_system_prompt()
    conversation: list[dict] = []
    for turn in history:
        role = turn.get("role")
        if role in ("user", "assistant") and turn.get("content"):
            conversation.append({"role": role, "content": turn["content"]})

    # Envuelve el mensaje en XML tags para estructura clara
    wrapped_message = f"<question>\n{message}\n</question>"
    conversation.append({"role": "user", "content": wrapped_message})

    try:
        reply = await _generate_reply(system, conversation)
    except Exception as e:  # noqa: BLE001
        print(f"CHAT_RAG error ({type(e).__name__}): {e} — fallback a chat clásico")
        from agent.chat import chat as classic_chat

        # El chat clásico vuelve a guardar el turno del usuario; para evitar
        # duplicado usamos su propio flujo con un session_id efímero de respuesta.
        return await classic_chat(message, session_id, db)

    reply = _append_sources_footer(reply)
    reply = _append_emergency_line_if_needed(reply)
    reply = scan_output(reply)
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
            messages.append(
                {
                    "role": "tool",
                    "tool_name": tc["name"],
                    "content": result,
                }
            )

    # Última pasada sin tools para que sintetice una respuesta final.
    final = await _ollama_chat(messages, use_tools=False)
    return (
        final.get("content") or "No pude generar una respuesta con los datos disponibles."
    ).strip()


async def _run_tool_loop_stream(messages: list[dict]) -> AsyncIterator[str]:
    """Variante en streaming de `_run_tool_loop()`.

    Copia paralela (no reemplaza `_run_tool_loop`, que sigue intacto y lo
    sigue usando `chat_rag()` sin cambios): las rondas de decisión de tools
    siguen usando `stream=False` porque necesitan el JSON completo de
    `tool_calls`. Solo la síntesis final —cuando el modelo ya tiene los
    resultados de las tools y redacta la respuesta— se transmite en vivo con
    `_ollama_chat_stream()`.
    """
    for round_num in range(MAX_TOOL_ROUNDS):
        message = await _ollama_chat(messages, use_tools=True)
        tool_calls = _extract_tool_calls(message)

        if not tool_calls:
            content = (message.get("content") or "").strip()
            if content:
                # Esta respuesta ya llegó completa en la misma llamada que
                # decidía si había tools que ejecutar; no hubo streaming en
                # esta ronda, así que se emite como un único chunk.
                yield content
                return
            # Sin contenido y sin tools → reintenta sin tools para forzar respuesta.
            break

        # Añade el turno del asistente (con sus tool_calls) y ejecuta cada tool.
        messages.append(message)
        for tc in tool_calls:
            result = await call_tool(tc["name"], tc["arguments"])
            print(f"  [tool] {tc['name']}({tc['arguments']}) → {result[:80]}...")
            messages.append(
                {
                    "role": "tool",
                    "tool_name": tc["name"],
                    "content": result,
                }
            )

    # Última pasada sin tools: síntesis final en streaming real.
    got_any = False
    async for piece in _ollama_chat_stream(messages):
        got_any = True
        yield piece
    if not got_any:
        yield "No pude generar una respuesta con los datos disponibles."


async def chat_rag_stream(message: str, session_id: str, db: AsyncSession) -> AsyncIterator[str]:
    """Variante en streaming de `chat_rag()`.

    Mismo loop de resolución de tools (vía `_run_tool_loop_stream`, que replica
    `_run_tool_loop` sin tocarlo), pero la síntesis final se transmite en vivo.

    Nota: igual que en `chat.py`, aquí no aplica ninguna lógica que necesite
    ver la respuesta completa antes de decidir descartarla. El pie de fuentes
    (`_append_sources_footer`) y la línea de emergencia
    (`_append_emergency_line_if_needed`) sí se aplican, pero solo pueden
    calcularse sobre el texto ya acumulado — se emiten como un chunk final
    extra justo antes de guardar el turno con `save_turn()`.
    """
    history = await get_history(session_id, db, limit=6)
    await save_turn(session_id, "user", message, db)

    # Igual que en chat_rag(): se atrapa aquí, no burbujea al 422 global —
    # un 422 a mitad de un stream SSE es inválido. Se emite el rechazo como
    # un chunk normal y se corta el stream ahí.
    try:
        message = validate_input(message)
    except PromptInjectionDetected as exc:
        reply = str(exc)
        yield reply
        await save_turn(session_id, "assistant", reply, db)
        return

    reset_sources()  # colector de fuentes para este request
    set_report_session(session_id)  # para la tool report_incident

    system = _build_system_prompt()
    conversation: list[dict] = []
    for turn in history:
        role = turn.get("role")
        if role in ("user", "assistant") and turn.get("content"):
            conversation.append({"role": role, "content": turn["content"]})
    conversation.append({"role": "user", "content": message})

    full_reply = ""
    try:
        async for piece in _generate_reply_stream(system, conversation):
            full_reply += piece
            yield piece
    except Exception as e:  # noqa: BLE001
        print(
            f"CHAT_RAG_STREAM error ({type(e).__name__}): {e} — fallback a chat clásico (streaming)"
        )
        from agent.chat import chat_stream as classic_chat_stream

        # Igual que en `chat_rag()`, el chat clásico vuelve a guardar el turno
        # del usuario y el de la respuesta por su cuenta (mismo trade-off ya
        # aceptado en el flujo no-streaming); no se debe duplicar aquí.
        async for piece in classic_chat_stream(message, session_id, db):
            yield piece
        return

    # scan_output solo puede aplicarse al remanente NO emitido todavía: el
    # cuerpo ya transmitido por SSE no se puede redactar retroactivamente
    # (limitación arquitectónica real, no un bug — documentado en el plan).
    before = full_reply
    full_reply = _append_sources_footer(full_reply)
    full_reply = _append_emergency_line_if_needed(full_reply)
    extra = scan_output(full_reply[len(before) :])
    if extra:
        yield extra
    await save_turn(session_id, "assistant", full_reply, db)


# --- Reutiliza la línea de emergencia del chat clásico ---
def _append_emergency_line_if_needed(text: str) -> str:
    from agent.chat import _append_emergency_line_if_needed as _impl

    return _impl(text)
