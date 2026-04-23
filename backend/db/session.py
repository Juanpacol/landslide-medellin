import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE_URL_SYNC = os.environ.get("DATABASE_URL_SYNC")

if not DATABASE_URL or not DATABASE_URL_SYNC:
    raise RuntimeError("DATABASE_URL y DATABASE_URL_SYNC deben estar definidas en backend/.env")

# asyncpg no usa sslmode=require como libpq; ssl=True exige TLS (equivalente práctico a require).
_async_connect_args = {"ssl": True, "timeout": 120}

_sync_connect_args = {"sslmode": "require"}

_async_url = make_url(DATABASE_URL)
# asyncpg rechaza sslmode en la URL si también se pasan connect_args.
if "sslmode" in _async_url.query:
    _async_url = _async_url.difference_update_query(["sslmode"])

async_engine = create_async_engine(
    _async_url,
    pool_pre_ping=True,
    connect_args=_async_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

sync_engine = create_engine(
    DATABASE_URL_SYNC,
    pool_pre_ping=True,
    connect_args=_sync_connect_args,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session, autoflush=False, expire_on_commit=False)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_engine():
    return sync_engine
