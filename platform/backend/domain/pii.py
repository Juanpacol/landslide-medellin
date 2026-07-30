"""Heuristic PII redaction in free text. Pure, no I/O.

Best-effort, NOT exhaustive: covers the most common patterns in Spanish/
Colombian free text (phone numbers, national IDs, emails). Does not replace
a human review of genuinely sensitive data.
"""

from __future__ import annotations

import re

# Colombian phone numbers: mobile (10 digits, starts with 3) or landline with
# area code, with or without separators. National ID (cédula): 6-10
# consecutive digits (no separators, so it doesn't swallow phone numbers
# already covered above — pattern order matters, applied most-specific to
# most-generic).
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL REDACTADO]"),
    (re.compile(r"(?:\+57\s?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[TELÉFONO REDACTADO]"),
    (re.compile(r"\b\d{1,3}(?:[.,]\d{3}){1,3}\b"), "[CÉDULA REDACTADA]"),
    (re.compile(r"\b\d{7,10}\b"), "[CÉDULA REDACTADA]"),
)


def redact_pii(text: str) -> str:
    """Replaces known PII patterns with markers. Does not otherwise modify
    the rest of the text or meaningfully change its length."""
    if not text:
        return text
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result
