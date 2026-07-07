"""
Configuración y clientes LLM compartidos (Anthropic primario, Ollama fallback).

El cliente lazy de Anthropic estaba duplicado en agent/chat_rag.py,
alerts/reports.py y agent/risk_explanations.py — tres copias del mismo
singleton. Este módulo es el único dueño de la conexión; la LÓGICA de
conversación (tools, streaming, prompts) sigue en agent/.
"""

from __future__ import annotations

import os
from typing import Any

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

_anthropic_client: Any = None


def get_anthropic_client() -> Any:
    """Cliente lazy: solo se construye (y solo exige ANTHROPIC_API_KEY) si
    realmente se llega a usar el proveedor Anthropic."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client
