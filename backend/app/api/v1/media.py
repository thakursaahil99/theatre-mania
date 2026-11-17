"""Signed object access for STORAGE_BACKEND=local (native development).

Plays the role S3/R2 presigned URLs play in production: every URL carries an HMAC over
(method, key, expiry). GET serves HLS segments/thumbnails; PUT receives admin uploads.
Disabled (404) unless local storage is active.
"""

import os
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.core import storage

router = APIRouter(prefix="/media", tags=["media"])

MAX_UPLOAD_BYTES = 5 * 1024**3


def _authorise(method: str, key: str, exp: int | None, sig: str | None) -> Path:
    if not storage.is_local():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    if exp is None or not sig or not storage.verify_local_signature(method, key, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Signature invalid or expired")
    try:
        return storage.local_path(key)
    except storage.InvalidKey:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bad key") from None


@router.get("/{key:path}", include_in_schema=False)
async def get_object(key: str, exp: int | None = None, sig: str | None = Query(None, max_length=128)) -> FileResponse:
    path = _authorise("GET", key, exp, sig)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    # The signature makes each URL unique, so caching it forever is safe.
    return FileResponse(path, media_type=storage.content_type_for(path),
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})  # fmt: skip


@router.put("/{key:path}", status_code=204, include_in_schema=False)
async def put_object(key: str, request: Request, exp: int | None = None, sig: str | None = Query(None, max_length=128)) -> None:
    path = _authorise("PUT", key, exp, sig)
    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    written = 0
    try:
        async with await anyio.open_file(tmp, "wb") as fh:
            async for chunk in request.stream():
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
                await fh.write(chunk)
        os.replace(tmp, path)  # atomic: the worker never sees a half-written file
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
