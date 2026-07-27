import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

try:
    from agent.chat import chat as _chat_impl  # type: ignore[import-not-found]
except ImportError:
    _chat_impl: Callable[..., Awaitable[str]] | None = None

# Variante streaming del chat clásico (sin RAG). Se usa desde chat_stream().
try:
    from agent.chat import chat_stream as _chat_stream_impl  # type: ignore[import-not-found]
except ImportError:
    _chat_stream_impl: Callable[..., AsyncIterator[str]] | None = None

# Chat con RAG + tools (Ollama tool-calling). Se activa con ENABLE_RAG=true.
try:
    from agent.chat_rag import chat_rag as _chat_rag_impl  # type: ignore[import-not-found]
except ImportError:
    _chat_rag_impl: Callable[..., Awaitable[str]] | None = None

# Variante streaming del chat con RAG + tools. Se usa desde chat_stream().
try:
    from agent.chat_rag import chat_rag_stream as _chat_rag_stream_impl  # type: ignore[import-not-found]
except ImportError:
    _chat_rag_stream_impl: Callable[..., AsyncIterator[str]] | None = None


def _rag_enabled() -> bool:
    # Default "true" para alinearlo con .env.example y docker-compose.yml, que
    # ya lo ponían en true. Con el default anterior ("false"), un despliegue
    # que olvidara la variable arrancaba con el chat SIN RAG y sin ningún
    # error visible — degradación silenciosa.
    return os.getenv("ENABLE_RAG", "true").strip().lower() in ("1", "true", "yes", "on")


try:
    from ml.predict import predict_all_comunas as _predict_all_impl  # type: ignore[import-not-found]
except ImportError:
    _predict_all_impl: Callable[..., Awaitable[None]] | None = None

try:
    from ml.predict import predict_risk as _predict_risk_impl  # type: ignore[import-not-found]
except ImportError:
    _predict_risk_impl: Callable[..., Awaitable[dict[str, Any]]] | None = None


async def chat(message: str, session_id: str, db: AsyncSession) -> str:
    # Si ENABLE_RAG=true y el chat con RAG está disponible, úsalo (Ollama + tools).
    if _rag_enabled() and _chat_rag_impl is not None:
        return await _chat_rag_impl(message, session_id, db)
    if _chat_impl is not None:
        return await _chat_impl(message, session_id, db)
    return (
        "Asistente TEYVA (modo demo): el módulo del Agente 2 aún no está enlazado. "
        f"Mensaje recibido ({len(message)} caracteres), sesión `{session_id}`."
    )


async def chat_stream(message: str, session_id: str, db: AsyncSession) -> AsyncIterator[str]:
    """Variante en streaming de `chat()`. Enruta según `ENABLE_RAG` exactamente
    igual que `chat()`, pero cede (yield) fragmentos de texto en vez de
    esperar la respuesta completa."""
    if _rag_enabled() and _chat_rag_stream_impl is not None:
        async for chunk in _chat_rag_stream_impl(message, session_id, db):
            yield chunk
        return
    if _chat_stream_impl is not None:
        async for chunk in _chat_stream_impl(message, session_id, db):
            yield chunk
        return
    yield "Streaming no disponible en este despliegue."


async def predict_all_comunas(db: AsyncSession) -> None:
    if _predict_all_impl is not None:
        await _predict_all_impl(db)
        return
    return None


async def predict_risk_stub(comuna_id: str, db: AsyncSession) -> dict[str, Any]:
    """Hasta que exista predict_risk del Agente 1."""
    if _predict_risk_impl is not None:
        try:
            cid = int(str(comuna_id))
        except ValueError:
            return {
                "commune_id": comuna_id,
                "risk_score": None,
                "detail": f"commune_id inválido: {comuna_id!r}",
            }
        out = await _predict_risk_impl(cid, db)
        out["commune_id"] = str(comuna_id)
        return out

    return {
        "commune_id": comuna_id,
        "risk_score": None,
        "detail": "predict_risk del Agente 1 no está disponible en este despliegue",
    }
