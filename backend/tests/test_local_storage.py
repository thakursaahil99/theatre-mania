"""STORAGE_BACKEND=local: on-disk objects behind HMAC-signed, expiring /media URLs."""

import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.core import storage
from app.core.config import settings


@pytest.fixture
def local_media(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "API_PUBLIC_URL", "http://testserver")
    storage.ensure_bucket()
    return tmp_path / "media"


def _path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def test_roundtrip_put_get_delete(local_media):
    storage.put_bytes("hls/a/360p/index.m3u8", b"#EXTM3U\n", "application/vnd.apple.mpegurl")
    assert storage.exists("hls/a/360p/index.m3u8")
    assert storage.get_text("hls/a/360p/index.m3u8") == "#EXTM3U\n"
    storage.delete_prefix("hls/a")
    assert not storage.exists("hls/a/360p/index.m3u8")


@pytest.mark.parametrize("key", ["../secret", "a/../../b", "/etc/passwd", "a\\b", "", "a//b"])
def test_traversal_is_rejected(local_media, key):
    with pytest.raises(storage.InvalidKey):
        storage.local_path(key)
    assert storage.exists(key) is False


def test_signature_binds_method_key_and_expiry(local_media):
    exp = int(time.time()) + 60
    sig = storage._local_sig("GET", "hls/a/seg.ts", exp)
    assert storage.verify_local_signature("GET", "hls/a/seg.ts", exp, sig)
    assert not storage.verify_local_signature("PUT", "hls/a/seg.ts", exp, sig)
    assert not storage.verify_local_signature("GET", "hls/b/seg.ts", exp, sig)
    assert not storage.verify_local_signature("GET", "hls/a/seg.ts", exp + 1, sig)
    expired = int(time.time()) - 1
    assert not storage.verify_local_signature("GET", "hls/a/seg.ts", expired, storage._local_sig("GET", "hls/a/seg.ts", expired))


async def test_media_route_serves_only_signed_urls(client, local_media):
    storage.put_bytes("hls/a/360p/seg_00000.ts", b"\x47" * 188, "video/mp2t")
    url = storage.presign_get("hls/a/360p/seg_00000.ts", 60)
    assert url.startswith("http://testserver/api/v1/media/hls/a/360p/seg_00000.ts?exp=")

    ok = await client.get(_path_and_query(url))
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "video/mp2t"
    assert "content-encoding" not in ok.headers  # never gzip video
    assert ok.content == b"\x47" * 188

    tampered = _path_and_query(url).replace("sig=", "sig=x")
    assert (await client.get(tampered)).status_code == 403
    assert (await client.get("/api/v1/media/hls/a/360p/seg_00000.ts?exp=9999999999&sig=nope")).status_code == 403
    assert (await client.get("/api/v1/media/hls/a/360p/seg_00000.ts")).status_code == 403  # unsigned hotlink
    # A valid signature for one object can't be replayed against another.
    other = _path_and_query(url).replace("seg_00000", "seg_00001")
    assert (await client.get(other)).status_code == 403


async def test_media_upload_via_signed_put(client, local_media):
    url = storage.presign_put("uploads/m/a/film.mp4", "video/mp4", 60)
    resp = await client.put(_path_and_query(url), content=b"fake-mp4-bytes", headers={"Content-Type": "video/mp4"})
    assert resp.status_code == 204
    assert (local_media / "uploads/m/a/film.mp4").read_bytes() == b"fake-mp4-bytes"
    assert not list(local_media.rglob("*.part"))
    # A GET signature can't be used to write.
    get_url = storage.presign_get("uploads/m/a/film.mp4", 60)
    assert (await client.put(_path_and_query(get_url), content=b"overwrite")).status_code == 403


async def test_media_route_disabled_for_s3_backend(client, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
    assert (await client.get("/api/v1/media/hls/a/seg.ts?exp=1&sig=x")).status_code == 404
