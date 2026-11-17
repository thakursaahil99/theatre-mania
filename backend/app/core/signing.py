"""Signed, expiring URLs for HLS segments (anti-hotlinking).

Two modes:
* s3  – each segment is an S3/R2 presigned GET (works anywhere, no CDN config needed).
* cdn – segments are served by a CDN / nginx edge validating `secure_link_md5`:
        md5 = base64url(md5("{expires}{uri} {secret}"))  →  {CDN_BASE_URL}{uri}?md5=..&expires=..
        See infra/nginx/nginx.conf for the matching edge config.
"""

import base64
import hashlib
import time

from app.core import storage
from app.core.config import settings


def _cdn_sign(uri: str, expires_at: int) -> str:
    raw = f"{expires_at}{uri} {settings.CDN_SIGNING_SECRET}".encode()
    return base64.urlsafe_b64encode(hashlib.md5(raw).digest()).decode().rstrip("=")  # noqa: S324 (nginx contract)


def signed_object_url(key: str, ttl: int | None = None) -> str:
    ttl = ttl or settings.SEGMENT_URL_TTL_SEC
    if settings.STREAM_SIGNING_MODE == "cdn":
        if not settings.CDN_BASE_URL or not settings.CDN_SIGNING_SECRET:
            raise RuntimeError("CDN signing mode requires CDN_BASE_URL and CDN_SIGNING_SECRET")
        expires_at = int(time.time()) + ttl
        uri = f"/{key.lstrip('/')}"
        return f"{settings.CDN_BASE_URL.rstrip('/')}{uri}?md5={_cdn_sign(uri, expires_at)}&expires={expires_at}"
    return storage.presign_get(key, ttl)


def verify_cdn_signature(uri: str, md5: str, expires: int) -> bool:
    """Reference implementation of the edge check (used in tests)."""
    if expires < time.time():
        return False
    return _cdn_sign(uri, expires) == md5
