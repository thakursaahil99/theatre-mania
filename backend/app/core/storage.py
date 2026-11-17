"""Object storage with two interchangeable backends (STORAGE_BACKEND).

* s3    – S3-compatible bucket: Cloudflare R2 in prod, SeaweedFS in docker compose.
          boto3 is synchronous; presigning is pure local HMAC so it is safe from async code,
          but network calls (get/put) must be wrapped with `run_in_threadpool`.
* local – plain files under LOCAL_MEDIA_DIR for native development without Docker. Browser
          access goes through the API's /media route using HMAC-signed, expiring URLs, so the
          anti-hotlinking guarantees are the same as presigned S3 URLs.
"""

import base64
import hashlib
import hmac
import mimetypes
import shutil
import time
from functools import lru_cache
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".m4s": "video/iso.segment",
    ".mp4": "video/mp4",
    ".vtt": "text/vtt",
    ".jpg": "image/jpeg",
}


def is_local() -> bool:
    return settings.STORAGE_BACKEND == "local"


def content_type_for(path: Path | PurePosixPath) -> str:
    return CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


# ============================================================================ local backend


class InvalidKey(ValueError):
    pass


def local_root() -> Path:
    return Path(settings.LOCAL_MEDIA_DIR).resolve()


def local_path(key: str) -> Path:
    """Resolve an object key to a file under the media root, refusing traversal."""
    if not key or "\\" in key or key.startswith("/") or any(p in {"", ".", ".."} for p in key.split("/")):
        raise InvalidKey(key)
    root = local_root()
    path = (root / key).resolve()
    if root not in path.parents:
        raise InvalidKey(key)
    return path


def _local_sig(method: str, key: str, expires_at: int) -> str:
    msg = f"{method}\n{key}\n{expires_at}".encode()
    digest = hmac.new(settings.JWT_SECRET.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def local_signed_url(method: str, key: str, expires: int) -> str:
    expires_at = int(time.time()) + expires
    base = f"{settings.API_PUBLIC_URL.rstrip('/')}{settings.API_V1_PREFIX}/media/{quote(key)}"
    return f"{base}?exp={expires_at}&sig={_local_sig(method, key, expires_at)}"


def verify_local_signature(method: str, key: str, expires_at: int, sig: str) -> bool:
    if expires_at < time.time():
        return False
    return hmac.compare_digest(_local_sig(method, key, expires_at), sig)


# ============================================================================ s3 backend


def _client(endpoint: str | None) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 4}),
    )


@lru_cache
def internal_client() -> BaseClient:
    return _client(settings.S3_ENDPOINT_URL)


@lru_cache
def public_client() -> BaseClient:
    """Signs URLs with the hostname browsers use (e.g. localhost vs. the docker service name)."""
    return _client(settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL)


# ============================================================================ public API


def presign_get(key: str, expires: int) -> str:
    if is_local():
        return local_signed_url("GET", key, expires)
    return public_client().generate_presigned_url(
        "get_object", Params={"Bucket": settings.S3_BUCKET, "Key": key}, ExpiresIn=expires
    )


def presign_put(key: str, content_type: str, expires: int = 3600) -> str:
    if is_local():
        return local_signed_url("PUT", key, expires)
    return public_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def get_text(key: str) -> str:
    if is_local():
        return local_path(key).read_text(encoding="utf-8")
    obj = internal_client().get_object(Bucket=settings.S3_BUCKET, Key=key)
    return obj["Body"].read().decode("utf-8")


def put_bytes(key: str, data: bytes, content_type: str, cache_control: str | None = None) -> None:
    if is_local():
        path = local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return
    extra = {"ContentType": content_type}
    if cache_control:
        extra["CacheControl"] = cache_control
    internal_client().put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data, **extra)


def download_file(key: str, dest: Path) -> None:
    if is_local():
        shutil.copyfile(local_path(key), dest)
        return
    internal_client().download_file(settings.S3_BUCKET, key, str(dest))


def exists(key: str) -> bool:
    if is_local():
        try:
            return local_path(key).is_file()
        except InvalidKey:
            return False
    try:
        internal_client().head_object(Bucket=settings.S3_BUCKET, Key=key)
        return True
    except ClientError:
        return False


def delete_object(key: str) -> None:
    if is_local():
        local_path(key).unlink(missing_ok=True)
        return
    internal_client().delete_object(Bucket=settings.S3_BUCKET, Key=key)


def upload_directory(local_dir: Path, prefix: str) -> list[str]:
    keys: list[str] = []
    client = None if is_local() else internal_client()
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        key = f"{prefix}/{path.relative_to(local_dir).as_posix()}"
        if client is None:
            dest = local_path(key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        else:
            client.upload_file(
                str(path),
                settings.S3_BUCKET,
                key,
                ExtraArgs={
                    "ContentType": content_type_for(path),
                    # Segments are content-addressed by asset id: cache forever at the CDN edge.
                    "CacheControl": "private, max-age=60" if path.suffix == ".m3u8" else "public, max-age=31536000, immutable",
                },
            )
        keys.append(key)
    return keys


def delete_prefix(prefix: str) -> None:
    if is_local():
        shutil.rmtree(local_path(prefix.rstrip("/")), ignore_errors=True)
        return
    client = internal_client()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.S3_BUCKET, Prefix=prefix.rstrip("/") + "/"):
        objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=settings.S3_BUCKET, Delete={"Objects": objects})


def ensure_bucket() -> None:
    if is_local():
        local_root().mkdir(parents=True, exist_ok=True)
        return
    client = internal_client()
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError:
        client.create_bucket(Bucket=settings.S3_BUCKET)
