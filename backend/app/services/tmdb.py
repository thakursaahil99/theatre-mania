"""Async TMDB client with Redis response caching (24h TTL by default).

All TMDB traffic goes through `TMDBClient._get`, which:
  * caches successful responses in Redis (key = path + sorted params),
  * negative-caches 404s for an hour,
  * retries once on 429 honouring Retry-After,
  * degrades gracefully (empty results) when no TMDB credentials are configured.
"""

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis import make_redis

log = logging.getLogger(__name__)

DETAIL_APPEND = "videos,credits,similar,recommendations,watch/providers,release_dates"
EMPTY_PAGE: dict[str, Any] = {"page": 1, "results": [], "total_pages": 0, "total_results": 0}


class TMDBError(Exception):
    pass


class TMDBNotFound(TMDBError):
    pass


class TMDBClient:
    def __init__(self, http: httpx.AsyncClient, redis: aioredis.Redis):
        self.http = http
        self.redis = redis

    @classmethod
    def build_http(cls) -> httpx.AsyncClient:
        headers = {"Accept": "application/json"}
        if settings.TMDB_READ_TOKEN:
            headers["Authorization"] = f"Bearer {settings.TMDB_READ_TOKEN}"
        return httpx.AsyncClient(
            base_url=settings.TMDB_BASE_URL,
            headers=headers,
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

    @classmethod
    @asynccontextmanager
    async def standalone(cls):
        """For Celery tasks / scripts that run outside the API event loop."""
        http = cls.build_http()
        redis = make_redis()
        try:
            yield cls(http, redis)
        finally:
            await http.aclose()
            await redis.aclose()

    @property
    def enabled(self) -> bool:
        return settings.tmdb_enabled

    @staticmethod
    def _cache_key(path: str, params: dict[str, Any]) -> str:
        raw = path + "?" + json.dumps(params, sort_keys=True, default=str)
        return "tmdb:v1:" + hashlib.sha1(raw.encode()).hexdigest()  # noqa: S324 (cache key)

    async def _cache_get(self, key: str) -> Any | None:
        try:
            cached = await self.redis.get(key)
        except RedisError:
            return None
        return json.loads(cached) if cached else None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self.redis.set(key, json.dumps(value), ex=ttl)
        except RedisError:
            log.warning("TMDB cache write failed", exc_info=True)

    async def _get(self, path: str, params: dict[str, Any] | None = None, ttl: int | None = None) -> Any:
        params = {"language": settings.TMDB_LANGUAGE, **{k: v for k, v in (params or {}).items() if v is not None}}
        key = self._cache_key(path, params)
        cached = await self._cache_get(key)
        if cached is not None:
            if isinstance(cached, dict) and cached.get("__not_found__"):
                raise TMDBNotFound(path)
            return cached

        query = dict(params)
        if not settings.TMDB_READ_TOKEN and settings.TMDB_API_KEY:
            query["api_key"] = settings.TMDB_API_KEY

        for attempt in range(2):
            try:
                resp = await self.http.get(path, params=query)
            except httpx.HTTPError as exc:
                raise TMDBError(f"TMDB unreachable: {exc}") from exc
            if resp.status_code == 429 and attempt == 0:
                await asyncio.sleep(min(float(resp.headers.get("Retry-After", "1")), 5))
                continue
            break

        if resp.status_code == 404:
            await self._cache_set(key, {"__not_found__": True}, 3600)
            raise TMDBNotFound(path)
        if resp.status_code >= 400:
            raise TMDBError(f"TMDB {resp.status_code} for {path}")

        data = resp.json()
        await self._cache_set(key, data, ttl or settings.TMDB_CACHE_TTL)
        return data

    # ---------------- Lists ----------------

    async def _page(self, path: str, **params: Any) -> dict[str, Any]:
        if not self.enabled:
            return EMPTY_PAGE
        return await self._get(path, params)

    async def trending(self, window: str = "week", page: int = 1) -> dict[str, Any]:
        return await self._page(f"/trending/movie/{window}", page=page)

    async def now_playing(self, page: int = 1) -> dict[str, Any]:
        return await self._page("/movie/now_playing", page=page, region=settings.TMDB_REGION)

    async def top_rated(self, page: int = 1) -> dict[str, Any]:
        return await self._page("/movie/top_rated", page=page)

    async def popular(self, page: int = 1) -> dict[str, Any]:
        return await self._page("/movie/popular", page=page)

    async def discover(self, page: int = 1, sort_by: str = "popularity.desc", **filters: Any) -> dict[str, Any]:
        return await self._page("/discover/movie", page=page, include_adult="false", sort_by=sort_by, **filters)

    async def search(self, query: str, page: int = 1, year: int | None = None) -> dict[str, Any]:
        return await self._page(
            "/search/movie", query=query, page=page, primary_release_year=year, include_adult="false"
        )

    # ---------------- Single title ----------------

    async def movie(self, tmdb_id: int) -> dict[str, Any]:
        if not self.enabled:
            raise TMDBNotFound("TMDB disabled")
        return await self._get(f"/movie/{tmdb_id}", {"append_to_response": DETAIL_APPEND})

    async def invalidate_movie(self, tmdb_id: int) -> None:
        params = {"language": settings.TMDB_LANGUAGE, "append_to_response": DETAIL_APPEND}
        try:
            await self.redis.delete(self._cache_key(f"/movie/{tmdb_id}", params))
        except RedisError:
            pass

    async def videos(self, tmdb_id: int) -> dict[str, Any]:
        if not self.enabled:
            return {"results": []}
        # English first, then anything (many films only have original-language trailers).
        return await self._get(f"/movie/{tmdb_id}/videos", {"include_video_language": "en,null"})

    async def genres(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        data = await self._get("/genre/movie/list", ttl=7 * 24 * 3600)
        return data.get("genres", [])

    async def search_one(self, title: str, year: int | None) -> dict[str, Any] | None:
        """Best match for a title/year (used by the seed script)."""
        data = await self.search(title, year=year)
        results = data.get("results", [])
        if not results and year:
            data = await self.search(title)
            results = [r for r in data.get("results", []) if (r.get("release_date") or "")[:4] in {str(year - 1), str(year), str(year + 1)}]
        return results[0] if results else None
