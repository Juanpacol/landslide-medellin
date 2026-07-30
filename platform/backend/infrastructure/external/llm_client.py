"""
Shared LLM configuration and clients (Anthropic primary, Ollama fallback).

The lazy Anthropic client used to be duplicated in agent/chat_rag.py,
alerts/reports.py and agent/risk_explanations.py — three copies of the same
singleton. This module is the sole owner of the connection; conversation
LOGIC (tools, streaming, prompts) stays in agent/.
"""

from __future__ import annotations

import os
from typing import Any

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

_anthropic_client: Any = None


def get_anthropic_client() -> Any:
    """Lazy client: only built (and only requires ANTHROPIC_API_KEY) if the
    Anthropic provider actually ends up being used."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client
