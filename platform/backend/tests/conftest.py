"""
Fixtures compartidas para los tests de integración de `agent/`.

Estos tests son de integración real (Postgres + Ollama), no unitarios con
mocks — por eso las fixtures abren conexiones reales en vez de fakes.
"""

import os

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from db.session import DATABASE_URL

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Sesión async real contra Postgres local.

    Crea una sesión nueva por test con rollback automático.
    Usa scope=function para evitar issues de event loop con asyncpg en macOS.
    """
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )

    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
        await engine.dispose()


@pytest.fixture
def require_ollama():
    """Salta el test si Ollama no está corriendo en local.

    Evita que un `pytest` corrido sin `ollama serve` levantado (p.ej. en CI)
    rompa la suite completa con errores de conexión.
    """
    try:
        res = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        res.raise_for_status()
    except Exception:
        pytest.skip("Ollama no está corriendo en local (OLLAMA_URL no responde)")
