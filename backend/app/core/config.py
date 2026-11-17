import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # APP_ENV_FILE lets tests (and alternative setups) avoid reading a developer's backend/.env.
    model_config = SettingsConfigDict(env_file=os.environ.get("APP_ENV_FILE", ".env"), extra="ignore", case_sensitive=True)

    # --- App ---
    ENV: Literal["dev", "test", "prod"] = "dev"
    PROJECT_NAME: str = "Theatre Mania"
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:3000"
    # Comma-separated list of allowed browser origins.
    CORS_ORIGINS: str = "http://localhost:3000"
    # Trust X-Forwarded-For (only enable behind a proxy you control).
    TRUST_PROXY_HEADERS: bool = False
    # Emails that are promoted to admin on signup / first Google login.
    ADMIN_EMAILS: str = ""

    # --- Database / cache ---
    DATABASE_URL: str = "postgresql+asyncpg://cineverse:cineverse@localhost:5432/cineverse"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    # --- Auth ---
    JWT_SECRET: str = Field(default="change-me-in-production-please-32+chars", min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MIN: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str | None = None
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    # Should point at the FRONTEND origin (proxied to the API) so cookies are first-party.
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/api/v1/auth/google/callback"

    # --- TMDB ---
    TMDB_READ_TOKEN: str | None = None  # v4 "API Read Access Token" (preferred)
    TMDB_API_KEY: str | None = None  # v3 key (fallback)
    TMDB_BASE_URL: str = "https://api.themoviedb.org/3"
    TMDB_LANGUAGE: str = "en-US"
    TMDB_REGION: str = "US"
    TMDB_CACHE_TTL: int = 60 * 60 * 24

    # --- Object storage ---
    # "s3":    S3-compatible bucket (Cloudflare R2 in prod, SeaweedFS in docker compose).
    # "local": files on disk under LOCAL_MEDIA_DIR, served by the API itself with HMAC-signed,
    #          expiring URLs. Zero-dependency native development (no Docker, no S3 server).
    STORAGE_BACKEND: Literal["s3", "local"] = "s3"
    LOCAL_MEDIA_DIR: str = "./data/media"
    # Browser-reachable base URL of this API (used for local-storage segment/upload URLs).
    API_PUBLIC_URL: str = "http://localhost:8000"
    # Scratch space for native mode (Celery filesystem broker, beat schedule).
    LOCAL_DATA_DIR: str = "./data"

    S3_ENDPOINT_URL: str | None = "http://localhost:9000"
    # Endpoint as reachable by *browsers* (used when presigning). Defaults to S3_ENDPOINT_URL.
    S3_PUBLIC_ENDPOINT_URL: str | None = None
    S3_REGION: str = "auto"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "cineverse-media"

    # --- Streaming ---
    # "s3": every segment URL is an S3 presigned URL.
    # "cdn": segment URLs point at CDN_BASE_URL signed with nginx secure_link_md5.
    STREAM_SIGNING_MODE: Literal["s3", "cdn"] = "s3"
    CDN_BASE_URL: str | None = None
    CDN_SIGNING_SECRET: str | None = None
    PLAYBACK_TOKEN_TTL_SEC: int = 60 * 60 * 4
    SEGMENT_URL_TTL_SEC: int = 60 * 60 * 6

    # --- Video pipeline ---
    FFMPEG_BIN: str = "ffmpeg"
    FFPROBE_BIN: str = "ffprobe"
    TRANSCODE_WORKDIR: str = "/tmp/cineverse"
    HLS_SEGMENT_SECONDS: int = 6
    X264_PRESET: str = "veryfast"
    # Hosts the import-from-URL pipeline is allowed to fetch from (SSRF guard).
    IMPORT_ALLOWED_HOSTS: str = "archive.org,.archive.org"

    # --- Limits / caching ---
    MAX_PROFILES: int = 4
    RATE_LIMIT_PER_MINUTE: int = 300
    HOME_CACHE_TTL: int = 300

    @property
    def redis_in_memory(self) -> bool:
        """REDIS_URL=memory:// → in-process store (native dev without a Redis server)."""
        return self.REDIS_URL.startswith("memory://")

    @property
    def celery_filesystem_broker(self) -> bool:
        return self.celery_broker.startswith("filesystem://")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}

    @property
    def import_allowed_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.IMPORT_ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def sync_database_url(self) -> str:
        url = self.DATABASE_URL
        return url.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")

    @property
    def celery_broker(self) -> str:
        if self.CELERY_BROKER_URL:
            return self.CELERY_BROKER_URL
        return "filesystem://" if self.redis_in_memory else self.REDIS_URL

    @property
    def celery_backend(self) -> str | None:
        # Task results are never read by the app, so native mode simply doesn't store them.
        if self.CELERY_RESULT_BACKEND:
            return self.CELERY_RESULT_BACKEND
        return None if self.redis_in_memory else self.REDIS_URL

    @property
    def tmdb_enabled(self) -> bool:
        return bool(self.TMDB_READ_TOKEN or self.TMDB_API_KEY)

    @property
    def google_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
