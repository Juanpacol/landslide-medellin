"""Guardrails del chat: detección heurística de prompt injection en la
entrada, redacción de PII en la salida.

Vive en agent/, no domain/: son reglas de prompt engineering específicas de
este chat, no reglas de negocio generales de TEYVA.

Heurísticos, NO exhaustivos — ni el estado del arte los resuelve al 100%.
Se prioriza no bloquear preguntas legítimas urgentes/agresivas (pánico real
de un ciudadano) sobre atrapar cada intento de manipulación posible.
"""

from __future__ import annotations

import logging
import re

from domain.pii import redact_pii
from errors.error_handler import ValidationError

logger = logging.getLogger(__name__)


class PromptInjectionDetected(ValidationError):
    pass


_REJECTION_MESSAGE = (
    "No puedo procesar ese mensaje tal como está escrito. Si tienes una "
    "pregunta sobre riesgo de deslizamientos, lluvia o una emergencia, "
    "cuéntamela de nuevo en tus propias palabras."
)

# Patrones de manipulación de instrucciones, no de contenido urgente/agresivo.
# Los ejemplos few-shot de _RAG_SYSTEM_SUFFIX ya cubren preguntas de pánico
# real ("se está cayendo la montaña") — esos NO deben matchear aquí.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignor[a-z]*\s+(tus|las|todas las)?\s*instruccion", re.IGNORECASE),
    re.compile(
        r"ignore\s+(your|all|previous|the)?\s*(all|previous)?\s*instructions", re.IGNORECASE
    ),
    re.compile(r"olvid[a-z]*\s+(todo\s+)?lo\s+anterior", re.IGNORECASE),
    re.compile(r"(eres|actúa como|actua como|act as)\s+(ahora\s+)?(un|una|otro)", re.IGNORECASE),
    re.compile(r"</question>", re.IGNORECASE),
    re.compile(r"<question>", re.IGNORECASE),
    re.compile(r"\bsystem\s*:\s*", re.IGNORECASE),
    re.compile(r"\[system\]", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(above|previous)", re.IGNORECASE),
)


def validate_input(message: str) -> str:
    """Lanza PromptInjectionDetected si el mensaje intenta romper la
    estructura XML del prompt o manipular las instrucciones del sistema.
    No modifica mensajes legítimos — los devuelve tal cual."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(message):
            logger.warning(
                "guardrails: posible prompt injection detectado",
                extra={"guardrail": "prompt_injection", "pattern": pattern.pattern},
            )
            raise PromptInjectionDetected(_REJECTION_MESSAGE)
    return message


def scan_output(text: str) -> str:
    """Redacta PII que el modelo pudiera repetir de vuelta (ej. si el
    usuario la incluyó en su pregunta y el modelo la cita). Segunda línea de
    defensa superficial: la defensa real es que el dato sensible nunca entre
    al contexto citable (ver domain/validation.py::validate_citizen_report,
    aplicado antes de guardar en citizen_reports)."""
    return redact_pii(text)
