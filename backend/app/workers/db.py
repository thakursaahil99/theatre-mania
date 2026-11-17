"""Synchronous SQLAlchemy session for Celery workers (psycopg driver)."""

from collections.abc import Iterator
from contextlib import contextmanager

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import configure_sqlite

engine = create_engine(settings.sync_database_url, pool_pre_ping=True, **({} if settings.sync_database_url.startswith("sqlite") else {"pool_size": 5, "max_overflow": 5}))
configure_sqlite(engine)
SyncSession = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SyncSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def invalidate_api_caches() -> None:
    if settings.redis_in_memory:
        return  # API caches live in the API process; short TTLs (HOME_CACHE_TTL) cover it
    try:
        client = redis.Redis.from_url(settings.REDIS_URL)
        client.delete("library:streamable_tmdb_ids:v1", "home:v1", "bollywood:v1")
        client.close()
    except redis.RedisError:
        pass
