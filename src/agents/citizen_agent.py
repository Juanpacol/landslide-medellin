"""
citizen_agent.py — Interfaz conversacional generativa para ciudadanos.

Este módulo expone la lógica del agente TEYVA como clase reutilizable
fuera del contexto de la API. Delega en platform/backend/agent/chat_rag.py.

Uso:
    from src.agents.citizen_agent import CitizenAgent
    agent = CitizenAgent()
    response = await agent.chat("¿Cuál es el riesgo en San Javier?", session_id="abc")
"""

from __future__ import annotations
import sys
from pathlib import Path

# Permite importar desde platform/backend sin instalar el paquete
_BACKEND = Path(__file__).resolve().parents[2] / "platform" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class CitizenAgent:
    """
    Agente conversacional TEYVA orientado a ciudadanos.

    Responde preguntas sobre riesgo de deslizamientos en las 21 comunas
    de Medellín en lenguaje natural, usando datos en tiempo real y RAG.
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or "default"

    async def chat(self, message: str, session_id: str | None = None) -> str:
        """
        Envía un mensaje al agente y retorna la respuesta.

        Args:
            message:    Pregunta del usuario en lenguaje natural.
            session_id: ID de sesión para mantener historial (opcional).

        Returns:
            Respuesta del agente como texto plano.
        """
        from agent.chat_rag import chat as _chat  # type: ignore
        sid = session_id or self.session_id
        return await _chat(message=message, session_id=sid)

    async def get_risk_summary(self, commune_id: str) -> str:
        """Retorna un resumen de riesgo para una comuna específica."""
        question = f"¿Cuál es el nivel de riesgo actual en la comuna {commune_id}?"
        return await self.chat(question)

    async def report_incident(self, commune: str, description: str, barrio: str = "") -> str:
        """Registra un reporte ciudadano de un evento observado."""
        msg = f"Quiero reportar lo siguiente en {commune}"
        if barrio:
            msg += f", barrio {barrio}"
        msg += f": {description}"
        return await self.chat(msg)
