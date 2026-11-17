import logging
import time

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis import get_redis

log = logging.getLogger(__name__)


def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        real = request.headers.get("x-real-ip")
        if real:
            return real
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Fixed-window limiter backed by Redis. Fails open if Redis is unavailable."""

    def __init__(self, times: int, seconds: int, scope: str | None = None):
        self.times = times
        self.seconds = seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        scope = self.scope or request.url.path
        window = int(time.time() // self.seconds)
        key = f"rl:{scope}:{client_ip(request)}:{window}"
        try:
            redis = get_redis()
            async with redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, self.seconds + 1)
                count, _ = await pipe.execute()
        except RedisError:
            log.warning("rate limiter unavailable; failing open", exc_info=True)
            return
        if count > self.times:
            retry_after = self.seconds - int(time.time() % self.seconds)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, slow down.",
                headers={"Retry-After": str(retry_after)},
            )


global_limiter = RateLimiter(settings.RATE_LIMIT_PER_MINUTE, 60, scope="global")
auth_limiter = RateLimiter(10, 60, scope="auth")
search_limiter = RateLimiter(90, 60, scope="search")
