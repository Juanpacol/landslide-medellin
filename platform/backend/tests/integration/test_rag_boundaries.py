"""
Test de límites de conocimiento (RAG boundaries) para el chatbot TEYVA.

Verifica que el `SYSTEM_PROMPT` efectivamente restrinja al modelo a su
dominio (riesgo de deslizamientos / clima / comunas de Medellín) y que no
"alucine" con conocimiento genérico de entrenamiento fuera de ese dominio.

Es un test de integración real: usa Ollama real (loop de tool-calling de
`chat_rag`), ChromaDB real y PostgreSQL real — no hay mocks. Por eso depende
de la fixture `require_ollama` (se salta si Ollama no está corriendo) y de
`db_session` (rollback automático al terminar).
"""

import uuid

import pytest

from agent.chat_rag import chat_rag
from agent.prompts import OUT_OF_SCOPE_REFUSAL

OUT_OF_SCOPE_QUESTIONS = [
    "¿Cuál es la capital de Japón?",
    "¿Cómo se hace un panettone?",
    "Cuéntame qué pasó en la Segunda Guerra Mundial",
    "Recomiéndame una película para ver hoy",
]

IN_SCOPE_QUESTIONS = [
    "¿Qué riesgo de deslizamiento hay en Villatina?",
    "¿Cuánta lluvia ha caído esta semana en Medellín?",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("question", OUT_OF_SCOPE_QUESTIONS)
async def test_refuses_out_of_scope_questions(require_ollama, db_session, question):
    session_id = f"test-boundary-{uuid.uuid4()}"
    reply = await chat_rag(question, session_id, db_session)

    # El bot debe rechazar preguntas fuera de scope. Buscar indicadores de rechazo:
    # - "no tengo datos", "no tengo información", "fuera", "no puedo responder sobre eso"
    rejection_markers = [
        "no tengo datos",
        "no tengo información",
        "fuera de",
        "no puedo responder",
        "conocimiento se limita",
        "no puedo ayudar",
    ]
    is_rejected = any(marker in reply.lower() for marker in rejection_markers)

    assert is_rejected, (
        f"El bot respondió fuera de su dominio a: {question!r}\n"
        f"Respuesta: {reply}\n"
        f"Esperaba un rechazo, pero el bot respondió normalmente."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("question", IN_SCOPE_QUESTIONS)
async def test_answers_in_scope_questions_without_refusing(require_ollama, db_session, question):
    session_id = f"test-boundary-{uuid.uuid4()}"
    reply = await chat_rag(question, session_id, db_session)
    assert OUT_OF_SCOPE_REFUSAL.lower() not in reply.lower(), (
        f"El bot rechazó una pregunta que SÍ está en su dominio: {question!r}\nRespuesta: {reply}"
    )
