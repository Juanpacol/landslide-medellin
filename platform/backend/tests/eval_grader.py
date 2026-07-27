"""
Graded scoring — uses an LLM judge (Ollama or Claude) to score prompt
outputs 1-10.

Complements the binary pass/fail validation in eval_runner.py with a
qualitative score + feedback, following the "grader" step of a standard
prompt evaluation workflow: draft prompt -> eval dataset -> run through
model -> run through grader -> score -> iterate.

Two providers, same rubric prompts, so scores are comparable side-by-side:
- "ollama" (default): local, free, no marginal cost — good for iterating.
- "anthropic": Claude (Haiku 4.5 by default) via the real API — used to
  cross-check whether Ollama's grading agrees with a stronger/independent
  judge. See test_grader_comparison.py for the side-by-side report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_BACKEND_ENV, override=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GRADER_MODEL = os.getenv("EVAL_GRADER_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2"))
GRADER_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
_anthropic_client = None


def _get_anthropic_client():
    """Lazily constructs the Anthropic client so importing this module never
    requires ANTHROPIC_API_KEY to be set (Ollama-only usage stays working)."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


# ── Grading prompts ──────────────────────────────────────────────────────────

_GRADE_CHAT_RAG_PROMPT = """Eres un evaluador estricto de un chatbot de riesgo de deslizamientos en Medellín.

Evalúa la RESPUESTA DEL BOT del 1 al 10 según esta rúbrica:
- 10: Responde correctamente, con datos precisos y completos, o rechaza apropiadamente una pregunta fuera de dominio.
- 7-9: Responde bien, con pequeños huecos de información o algo de verbosidad.
- 4-6: Responde pero de forma incompleta, vaga, o con formato confuso.
- 1-3: Incorrecta, alucina datos, o falla en rechazar una pregunta fuera de dominio (o rechaza una que sí es válida).

PREGUNTA DEL USUARIO:
{question}

RESPUESTA DEL BOT:
{response}

Responde ÚNICAMENTE con un objeto JSON, sin texto adicional, con esta forma exacta:
{{"score": <entero 1-10>, "feedback": "razón concisa en una frase"}}"""

_GRADE_RISK_EXPLANATION_PROMPT = """Eres un evaluador estricto de explicaciones de riesgo de deslizamientos para operarios de campo en Medellín.

Evalúa la EXPLICACIÓN del 1 al 10 según esta rúbrica:
- 10: Estructura clara, factores concretos con datos reales, urgencia correcta para la categoría, acción específica y accionable.
- 7-9: Estructura correcta, factores mayormente concretos, acción razonable.
- 4-6: Estructura presente pero vaga, factores genéricos, o acción poco clara.
- 1-3: Sin estructura útil, lenguaje vago ("podría", "tal vez"), o inconsistente con la categoría de riesgo.

CATEGORÍA DE RIESGO: {category}
PRECIPITACIÓN 7 DÍAS: {precip}mm
EVENTOS RECIENTES: {n_events}

EXPLICACIÓN GENERADA:
{explanation_text}

Responde ÚNICAMENTE con un objeto JSON, sin texto adicional, con esta forma exacta:
{{"score": <entero 1-10>, "feedback": "razón concisa en una frase"}}"""

_GRADE_SLACK_PAYLOAD_PROMPT = """Eres un evaluador estricto de mensajes de alerta de Slack para un sistema de monitoreo de riesgo de deslizamientos.

Evalúa el PAYLOAD del 1 al 10 según esta rúbrica:
- 10: Formato claro y profesional, información accionable de un vistazo, urgencia bien comunicada.
- 7-9: Formato correcto, mensaje útil con pequeñas mejoras posibles de claridad.
- 4-6: Formato válido pero el mensaje es confuso o le falta contexto útil.
- 1-3: Formato roto, mensaje inútil o urgencia mal comunicada.

CATEGORÍA DE RIESGO: {risk_category}
PAYLOAD (bloques de Slack, texto plano extraído):
{payload_text}

Responde ÚNICAMENTE con un objeto JSON, sin texto adicional, con esta forma exacta:
{{"score": <entero 1-10>, "feedback": "razón concisa en una frase"}}"""


def _extract_json(raw: str) -> dict | None:
    """Extracts a JSON object from a raw LLM response, tolerating extra text."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


async def _call_ollama_grader(prompt: str) -> dict:
    """Calls Ollama with a grading prompt, returns validated {score, feedback}.

    On any failure (connection, parse, out-of-range score) returns
    {"score": None, "feedback": "<error reason>"} so callers can treat
    missing grading as a skip rather than crash the whole eval run.
    """
    payload: dict[str, Any] = {
        "model": GRADER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 150},
    }

    try:
        async with httpx.AsyncClient(timeout=GRADER_TIMEOUT) as client:
            res = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        res.raise_for_status()
        content = (res.json().get("message") or {}).get("content", "")
    except Exception as exc:
        logger.warning("Grader Ollama call failed: %s", exc)
        return {"score": None, "feedback": f"grader_error: {exc}"}

    parsed = _extract_json(content)
    if parsed is None:
        logger.warning("Grader returned unparsable content: %r", content[:200])
        return {"score": None, "feedback": "grader_error: unparsable JSON response"}

    score = parsed.get("score")
    feedback = parsed.get("feedback", "")

    if not isinstance(score, (int, float)) or not (1 <= score <= 10):
        logger.warning("Grader returned out-of-range score: %r", score)
        return {"score": None, "feedback": f"grader_error: invalid score {score!r}"}

    return {
        "score": int(score),
        "feedback": str(feedback),
        "grader_model": f"ollama/{GRADER_MODEL}",
    }


def _call_anthropic_grader_sync(prompt: str) -> dict:
    """Sync Anthropic call — wrapped in asyncio.to_thread by the async entrypoint
    so callers keep the same `await grade_*()` interface regardless of provider."""
    try:
        client = _get_anthropic_client()
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Grader Anthropic call failed: %s", exc)
        return {
            "score": None,
            "feedback": f"grader_error: {exc}",
            "grader_model": f"anthropic/{ANTHROPIC_MODEL}",
        }

    if response.stop_reason == "refusal":
        return {
            "score": None,
            "feedback": "grader_error: refused",
            "grader_model": f"anthropic/{ANTHROPIC_MODEL}",
        }

    content = next((b.text for b in response.content if b.type == "text"), "")
    parsed = _extract_json(content)
    if parsed is None:
        logger.warning("Grader returned unparsable content: %r", content[:200])
        return {
            "score": None,
            "feedback": "grader_error: unparsable JSON response",
            "grader_model": f"anthropic/{ANTHROPIC_MODEL}",
        }

    score = parsed.get("score")
    feedback = parsed.get("feedback", "")

    if not isinstance(score, (int, float)) or not (1 <= score <= 10):
        logger.warning("Grader returned out-of-range score: %r", score)
        return {
            "score": None,
            "feedback": f"grader_error: invalid score {score!r}",
            "grader_model": f"anthropic/{ANTHROPIC_MODEL}",
        }

    return {
        "score": int(score),
        "feedback": str(feedback),
        "grader_model": f"anthropic/{ANTHROPIC_MODEL}",
    }


async def _call_anthropic_grader(prompt: str) -> dict:
    return await asyncio.to_thread(_call_anthropic_grader_sync, prompt)


async def _dispatch_grader(prompt: str, provider: str) -> dict:
    if provider == "anthropic":
        return await _call_anthropic_grader(prompt)
    if provider == "ollama":
        return await _call_ollama_grader(prompt)
    raise ValueError(f"Unknown grader provider: {provider!r} (expected 'ollama' or 'anthropic')")


async def grade_chat_rag_response(question: str, response: str, provider: str = "ollama") -> dict:
    """Grades a chat_rag response 1-10 using the given provider as judge."""
    prompt = _GRADE_CHAT_RAG_PROMPT.format(question=question, response=response)
    return await _dispatch_grader(prompt, provider)


async def grade_risk_explanation(
    category: str,
    precip: float,
    n_events: int,
    explanation_text: str,
    provider: str = "ollama",
) -> dict:
    """Grades a risk explanation 1-10 using the given provider as judge."""
    prompt = _GRADE_RISK_EXPLANATION_PROMPT.format(
        category=category,
        precip=precip,
        n_events=n_events,
        explanation_text=explanation_text,
    )
    return await _dispatch_grader(prompt, provider)


async def grade_slack_webhook(payload: dict, risk_category: str, provider: str = "ollama") -> dict:
    """Grades a Slack webhook payload 1-10 using the given provider as judge."""
    # Flatten blocks to plain text so the grader reads it like a human would.
    texts = []
    for block in payload.get("blocks", []):
        text_obj = block.get("text")
        if isinstance(text_obj, dict) and "text" in text_obj:
            texts.append(text_obj["text"])
    payload_text = "\n".join(texts) if texts else json.dumps(payload, ensure_ascii=False)

    prompt = _GRADE_SLACK_PAYLOAD_PROMPT.format(
        risk_category=risk_category,
        payload_text=payload_text,
    )
    return await _dispatch_grader(prompt, provider)
