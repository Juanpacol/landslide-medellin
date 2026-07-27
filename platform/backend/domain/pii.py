"""Redacción heurística de PII en texto libre. Puro, sin I/O.

Best-effort, NO exhaustivo: cubre los patrones más comunes en texto libre en
español/Colombia (teléfonos, cédulas, emails). No reemplaza una revisión
humana de datos sensibles reales.
"""

from __future__ import annotations

import re

# Teléfonos CO: celular (10 dígitos, empieza en 3) o fijo con indicativo,
# con o sin separadores. Cédula: 6-10 dígitos consecutivos (sin separadores,
# para no comerse números de teléfono ya cubiertos arriba — el orden de los
# patrones importa, se aplican de más específico a más genérico).
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL REDACTADO]"),
    (re.compile(r"(?:\+57\s?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[TELÉFONO REDACTADO]"),
    (re.compile(r"\b\d{1,3}(?:[.,]\d{3}){1,3}\b"), "[CÉDULA REDACTADA]"),
    (re.compile(r"\b\d{7,10}\b"), "[CÉDULA REDACTADA]"),
)


def redact_pii(text: str) -> str:
    """Reemplaza patrones de PII conocidos por marcadores. No modifica el
    resto del texto ni su longitud de forma significativa."""
    if not text:
        return text
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result
