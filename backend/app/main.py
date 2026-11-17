import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import media
from app.api.v1.router import api_router
from app.core import storage
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.middleware import OriginCheckMiddleware, SecurityHeadersMiddleware
from app.core.redis import close_redis, get_redis
from app.services.tmdb import TMDBClient, TMDBError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MEDIA_PREFIX = f"{settings.API_V1_PREFIX}/media/"


class SelectiveGZipMiddleware(GZipMiddleware):
    """Gzip API responses, but never video segments (already compressed; breaks Range)."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(MEDIA_PREFIX):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = TMDBClient.build_http()
    app.state.tmdb = TMDBClient(app.state.http, get_redis())
    if storage.is_local():
        storage.ensure_bucket()  # creates LOCAL_MEDIA_DIR
    yield
    await app.state.http.aclose()
    await close_redis()


app = FastAPI(
    title=f"{settings.PROJECT_NAME} API",
    version="1.0.0",
    description="Streaming API. Only licensed / public-domain titles are streamable; "
    "everything else exposes metadata and official trailers only.",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    lifespan=lifespan,
)

# Order matters: the last added runs first.
app.add_middleware(SelectiveGZipMiddleware, minimum_size=1024)
app.add_middleware(OriginCheckMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Profile-Id"],
    max_age=600,
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
# Signed media sits outside the global rate limit: a single viewer fetches a segment every few seconds.
app.include_router(media.router, prefix=settings.API_V1_PREFIX)


@app.exception_handler(TMDBError)
async def tmdb_error_handler(_: Request, exc: TMDBError) -> JSONResponse:
    return JSONResponse({"detail": "Metadata provider unavailable"}, status_code=502)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    checks = {"db": False, "redis": False}
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        checks["redis"] = bool(await get_redis().ping())
    except Exception:  # noqa: BLE001
        pass
    return {"status": "ok" if all(checks.values()) else "degraded", **checks}
