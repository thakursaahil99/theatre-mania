from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"timeout": 30}}
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20, "pool_recycle": 1800}


def configure_sqlite(engine: Engine | AsyncEngine) -> None:
    """Make SQLite safe for the native dev setup, where the API and the Celery worker
    share one database file: WAL lets readers and a writer coexist, busy_timeout waits
    for locks instead of failing, and foreign keys are enforced like on Postgres."""
    sync_engine = engine.sync_engine if isinstance(engine, AsyncEngine) else engine
    if sync_engine.dialect.name != "sqlite":
        return

    @event.listens_for(sync_engine, "connect")
    def _pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - exercised in native mode
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))
configure_sqlite(engine)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
