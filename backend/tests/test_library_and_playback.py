import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core import signing, storage
from app.core.time import utcnow
from app.models import AssetStatus, License, VideoAsset

MASTER = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=480x360
360p/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=960x720
720p/index.m3u8
"""
VARIANT = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:6.000,
seg_00000.ts
#EXTINF:4.000,
seg_00001.ts
#EXT-X-ENDLIST
"""

PD_LICENSE = {"license_type": "public_domain", "licensor": "Public domain", "territories": ["us"]}


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    objects = {}

    def get_text(key: str) -> str:
        if key.endswith("master.m3u8"):
            return MASTER
        if key.endswith("index.m3u8"):
            return VARIANT
        return objects[key]

    monkeypatch.setattr(storage, "get_text", get_text)
    monkeypatch.setattr(storage, "presign_get", lambda key, expires: f"https://bucket.test/{key}?sig=abc&exp={expires}")
    monkeypatch.setattr(storage, "put_bytes", lambda key, data, ct, cc=None: objects.__setitem__(key, data.decode()))
    return objects


async def _ready_asset(session_factory, movie_id: str) -> str:
    async with session_factory() as db:
        asset = VideoAsset(
            movie_id=uuid.UUID(movie_id),
            status=AssetStatus.ready,
            storage_prefix="hls/test",
            master_key="hls/test/master.m3u8",
            duration_seconds=600.0,
            renditions=[{"name": "360p", "height": 360}, {"name": "720p", "height": 720}],
            intro_start_sec=5,
            intro_end_sec=40,
        )
        db.add(asset)
        await db.commit()
        return str(asset.id)


async def _publish_title(admin_client, session_factory, tmdb_id: int = 10331) -> dict:
    created = await admin_client.post("/api/v1/admin/movies", json={"tmdb_id": tmdb_id, "license": PD_LICENSE})
    assert created.status_code == 201, created.text
    movie = created.json()
    assert movie["status"] == "draft" and movie["license_active"] is True
    assert movie["license"]["territories"] == ["US"]

    # Can't publish before a video asset is ready.
    assert (await admin_client.post(f"/api/v1/admin/movies/{movie['id']}/publish")).status_code == 409
    await _ready_asset(session_factory, movie["id"])
    published = await admin_client.post(f"/api/v1/admin/movies/{movie['id']}/publish")
    assert published.status_code == 200 and published.json()["status"] == "published"
    return published.json()


async def test_non_admin_cannot_use_admin_api(user_client):
    assert (await user_client.get("/api/v1/admin/movies")).status_code == 403


async def test_full_library_flow(admin_client, session_factory):
    c = admin_client
    movie = await _publish_title(c, session_factory)
    assert movie["title"] == "Night of the Living Dead"
    assert movie["slug"] == "night-of-the-living-dead-1968"

    # Duplicate TMDB titles are rejected.
    dup = await c.post("/api/v1/admin/movies", json={"tmdb_id": 10331, "license": PD_LICENSE})
    assert dup.status_code == 409

    # Detail page now offers Watch Now, home has a Free to Watch row.
    detail = (await c.get("/api/v1/movies/10331")).json()
    assert detail["availability"]["streamable"] is True
    assert detail["availability"]["license_type"] == "public_domain"
    home = (await c.get("/api/v1/movies/home")).json()
    free = next(r for r in home["rows"] if r["id"] == "free")
    assert free["items"][0]["id"] == "10331"
    trending = next(r for r in home["rows"] if r["id"] == "trending")
    assert next(i for i in trending["items"] if i["id"] == "10331")["streamable"] is True

    # Start playback.
    start = await c.post("/api/v1/playback/10331/start")
    assert start.status_code == 200, start.text
    pb = start.json()
    assert pb["resume_position_sec"] == 0
    assert pb["intro_end_sec"] == 40

    # Master playlist is rewritten to tokenised API variant URLs.
    master = await c.get(pb["master_url"])
    assert master.status_code == 200
    assert master.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    token = parse_qs(urlsplit(pb["master_url"]).query)["token"][0]
    assert f"v/360p.m3u8?token={token}" in master.text
    assert "360p/index.m3u8" not in master.text

    # Variant playlist segments are signed URLs straight to storage.
    variant = await c.get(f"/api/v1/stream/{pb['asset_id']}/v/720p.m3u8", params={"token": token})
    assert variant.status_code == 200
    assert "https://bucket.test/hls/test/720p/seg_00000.ts?sig=abc" in variant.text
    assert (await c.get(f"/api/v1/stream/{pb['asset_id']}/v/1080p.m3u8", params={"token": token})).status_code == 404
    assert (await c.get(f"/api/v1/stream/{pb['asset_id']}/v/720p.m3u8", params={"token": "junk"})).status_code == 403
    other = uuid.uuid4()
    assert (await c.get(f"/api/v1/stream/{other}/master.m3u8", params={"token": token})).status_code == 403

    # Heartbeats feed continue-watching and analytics.
    hb = await c.post(f"/api/v1/playback/sessions/{pb['session_id']}/heartbeat",
                      json={"position_sec": 120, "duration_sec": 600, "watched_delta_sec": 115})  # fmt: skip
    assert hb.status_code == 204
    cw = (await c.get("/api/v1/me/continue-watching")).json()
    assert cw[0]["movie"]["id"] == "10331" and cw[0]["position_sec"] == 120

    again = (await c.post("/api/v1/playback/10331/start")).json()
    assert again["resume_position_sec"] == 117  # resumes with a little pre-roll
    renewed = (await c.post("/api/v1/playback/10331/start", params={"session_id": again["session_id"]})).json()
    assert renewed["session_id"] == again["session_id"]  # token renewal doesn't count a new view

    stats = (await c.get("/api/v1/admin/analytics", params={"days": 7})).json()
    assert stats["views"] == 2
    assert stats["unique_viewers"] == 1
    assert stats["top_movies"][0]["title"] == "Night of the Living Dead"
    assert len(stats["daily"]) == 7

    # Finishing the movie removes it from continue-watching.
    await c.post(f"/api/v1/playback/sessions/{again['session_id']}/heartbeat",
                 json={"position_sec": 590, "duration_sec": 600, "watched_delta_sec": 60})  # fmt: skip
    assert (await c.get("/api/v1/me/continue-watching")).json() == []
    assert (await c.get("/api/v1/me/history")).json()[0]["completed"] is True


async def test_expired_license_blocks_streaming(admin_client, session_factory):
    movie = await _publish_title(admin_client, session_factory)
    async with session_factory() as db:
        lic = await db.get(License, uuid.UUID(movie["license"]["id"]))
        lic.expires_at = utcnow() - timedelta(minutes=1)
        await db.commit()
    from app.services.catalog import invalidate_library_cache

    await invalidate_library_cache()
    assert (await admin_client.post("/api/v1/playback/10331/start")).status_code == 403
    detail = (await admin_client.get("/api/v1/movies/10331")).json()
    assert detail["availability"]["streamable"] is False


async def test_watchlist_and_ratings_work_for_any_title(user_client):
    c = user_client
    assert (await c.put("/api/v1/me/watchlist/3085")).status_code == 204
    assert (await c.put("/api/v1/me/watchlist/3085")).status_code == 204  # idempotent
    wl = (await c.get("/api/v1/me/watchlist")).json()
    assert [m["id"] for m in wl] == ["3085"] and wl[0]["streamable"] is False

    state = (await c.put("/api/v1/me/ratings/3085", json={"score": 4})).json()
    assert state == {"in_watchlist": True, "rating": 4, "position_sec": None, "duration_sec": None, "completed": False}
    assert (await c.put("/api/v1/me/ratings/3085", json={"score": 9})).status_code == 422

    assert (await c.delete("/api/v1/me/watchlist/3085")).status_code == 204
    assert (await c.get("/api/v1/me/watchlist")).json() == []
    assert (await c.put("/api/v1/me/watchlist/999999")).status_code == 404


async def test_subtitle_upload_converts_srt(admin_client, session_factory, fake_storage):
    movie = await _publish_title(admin_client, session_factory)
    asset_id = movie["assets"][0]["id"]
    srt = "1\n00:00:01,000 --> 00:00:02,500\nHello.\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld.\n"
    r = await admin_client.post(
        f"/api/v1/admin/assets/{asset_id}/subtitles",
        data={"language": "en", "label": "English", "is_default": "true"},
        files={"file": ("subs.srt", srt.encode(), "application/x-subrip")},
    )
    assert r.status_code == 201, r.text
    stored = next(iter(fake_storage.values()))
    assert stored.startswith("WEBVTT") and "00:00:01.000 --> 00:00:02.500" in stored

    pb = (await admin_client.post("/api/v1/playback/10331/start")).json()
    assert pb["subtitles"][0]["label"] == "English"
    vtt = await admin_client.get(pb["subtitles"][0]["url"])
    assert vtt.status_code == 200 and vtt.text.startswith("WEBVTT")


def test_cdn_signature_roundtrip(monkeypatch):
    monkeypatch.setattr(signing.settings, "STREAM_SIGNING_MODE", "cdn")
    monkeypatch.setattr(signing.settings, "CDN_BASE_URL", "https://cdn.test")
    monkeypatch.setattr(signing.settings, "CDN_SIGNING_SECRET", "s3cr3t")
    url = signing.signed_object_url("hls/a/720p/seg_00001.ts", ttl=60)
    parts = urlsplit(url)
    q = parse_qs(parts.query)
    assert parts.netloc == "cdn.test"
    assert signing.verify_cdn_signature(parts.path, q["md5"][0], int(q["expires"][0]))
    assert not signing.verify_cdn_signature("/hls/b/720p/seg_00001.ts", q["md5"][0], int(q["expires"][0]))
