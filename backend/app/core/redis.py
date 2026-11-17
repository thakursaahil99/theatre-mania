"""Process-wide async Redis client (swappable in tests).

REDIS_URL=memory:// uses an in-process Redis emulation (fakeredis) so native development
needs no Redis server. Caches and rate-limit counters are then per-process, which is fine
for a single local API process; use a real Redis anywhere you run more than one.
"""

import redis.asyncio as aioredis

from app.core.config import settings

_client: aioredis.Redis | None = None


def make_redis() -> aioredis.Redis:
    if settings.redis_in_memory:
        import fakeredis  # dev dependency; only imported in memory mode

        return fakeredis.FakeAsyncRedis(decode_responses=True)
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = make_redis()
    return _client


def set_redis(client: aioredis.Redis) -> None:
    global _client
    _client = client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
