"""Tokenised HLS playlists.

hls.js requests the master playlist from the API (same-origin through the Next.js proxy).
We rewrite variant URIs back to the API and, in each variant playlist, replace every
segment URI with a signed, expiring URL straight to the bucket/CDN. Without a valid
playback token nobody can obtain segment URLs, and harvested URLs die after the TTL.
"""

import re
import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from redis.exceptions import RedisError

from app.api.deps import DB
from app.core import signing, storage
from app.core.redis import get_redis
from app.core.security import TokenError, decode_token
from app.models import AssetStatus, Subtitle, VideoAsset

router = APIRouter(prefix="/stream", tags=["stream"])

HLS_MIME = "application/vnd.apple.mpegurl"
NO_STORE = {"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"}
RENDITION_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
URI_ATTR_RE = re.compile(r'URI="([^"]+)"')


def _authorise(token: str, asset_id: uuid.UUID) -> None:
    try:
        payload = decode_token(token, "playback")
    except TokenError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Playback token invalid or expired") from None
    if payload.get("aid") != str(asset_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Token does not match this stream")


async def _ready_asset(db: DB, asset_id: uuid.UUID) -> VideoAsset:
    asset = await db.get(VideoAsset, asset_id)
    if asset is None or asset.status != AssetStatus.ready or not asset.storage_prefix:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Stream not found")
    return asset


async def _object_text(key: str) -> str:
    """Playlists are immutable after transcoding, so cache them in Redis."""
    cache_key = f"obj:{key}"
    redis = get_redis()
    try:
        if cached := await redis.get(cache_key):
            return cached
    except RedisError:
        pass
    try:
        text = await run_in_threadpool(storage.get_text, key)
    except Exception as exc:  # botocore raises many types
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Playlist missing") from exc
    try:
        await redis.set(cache_key, text, ex=3600)
    except RedisError:
        pass
    return text


def rewrite_master(text: str, token: str) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            rendition = stripped.split("/")[0]
            if not RENDITION_RE.match(rendition):
                continue
            out.append(f"v/{rendition}.m3u8?token={token}")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def rewrite_variant(text: str, key_prefix: str) -> str:
    def sign(uri: str) -> str:
        if uri.startswith(("http://", "https://")):
            return uri
        return signing.signed_object_url(f"{key_prefix}/{uri.lstrip('/')}")

    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # EXT-X-MAP / EXT-X-KEY carry URIs too (fMP4 init segments, keys).
            out.append(URI_ATTR_RE.sub(lambda m: f'URI="{sign(m.group(1))}"', line) if "URI=" in line else line)
        else:
            out.append(sign(stripped))
    return "\n".join(out) + "\n"


@router.get("/{asset_id}/master.m3u8")
async def master_playlist(asset_id: uuid.UUID, db: DB, token: str = Query(..., max_length=2048)) -> Response:
    _authorise(token, asset_id)
    asset = await _ready_asset(db, asset_id)
    text = await _object_text(asset.master_key or f"{asset.storage_prefix}/master.m3u8")
    return Response(rewrite_master(text, token), media_type=HLS_MIME, headers=NO_STORE)


@router.get("/{asset_id}/v/{rendition}.m3u8")
async def variant_playlist(
    asset_id: uuid.UUID, rendition: str, db: DB, token: str = Query(..., max_length=2048)
) -> Response:
    _authorise(token, asset_id)
    if not RENDITION_RE.match(rendition):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bad rendition")
    asset = await _ready_asset(db, asset_id)
    known = {r.get("name") for r in (asset.renditions or [])}
    if rendition not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown rendition")
    prefix = f"{asset.storage_prefix}/{rendition}"
    text = await _object_text(f"{prefix}/index.m3u8")
    body = await run_in_threadpool(rewrite_variant, text, prefix)
    return Response(body, media_type=HLS_MIME, headers=NO_STORE)


@router.get("/{asset_id}/subtitles/{subtitle_id}.vtt")
async def subtitle_track(
    asset_id: uuid.UUID, subtitle_id: uuid.UUID, db: DB, token: str = Query(..., max_length=2048)
) -> Response:
    _authorise(token, asset_id)
    sub = await db.get(Subtitle, subtitle_id)
    if sub is None or sub.asset_id != asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subtitle not found")
    return Response(
        await _object_text(sub.storage_key), media_type="text/vtt", headers={"Cache-Control": "private, max-age=600"}
    )
