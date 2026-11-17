from tests.conftest import signup


async def test_signup_sets_cookies_and_default_profile(client):
    body = await signup(client)
    assert body["user"]["email"] == "viewer@example.com"
    assert body["user"]["is_admin"] is False
    assert body["active_profile_id"]
    assert "cv_access" in client.cookies
    assert "cv_refresh" in client.cookies

    profiles = (await client.get("/api/v1/profiles")).json()
    assert len(profiles) == 1 and profiles[0]["name"] == "viewer"


async def test_signup_rejects_duplicates_and_weak_passwords(client):
    await signup(client)
    dup = await client.post("/api/v1/auth/signup", json={"email": "VIEWER@example.com", "password": "popcorn-42"})
    assert dup.status_code == 409
    weak = await client.post("/api/v1/auth/signup", json={"email": "x@example.com", "password": "12345678"})
    assert weak.status_code == 422


async def test_admin_emails_are_promoted(client):
    body = await signup(client, email="admin@example.com")
    assert body["user"]["is_admin"] is True


async def test_login_and_me(client):
    await signup(client)
    client.cookies.clear()
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    bad = await client.post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "nope-nope-1"})
    assert bad.status_code == 401
    ok = await client.post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "popcorn-42"})
    assert ok.status_code == 200
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["user"]["email"] == "viewer@example.com"


async def test_refresh_rotation_and_reuse_detection(client):
    await signup(client)
    old_refresh = client.cookies.get("cv_refresh")

    first = await client.post("/api/v1/auth/refresh")
    assert first.status_code == 200
    assert client.cookies.get("cv_refresh") != old_refresh

    # Replaying the rotated-out token revokes the whole family...
    client.cookies.set("cv_refresh", old_refresh, path="/api/v1/auth")
    replay = await client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    # ...including the token that was legitimately issued by the first refresh.
    client.cookies.clear()
    client.cookies.set("cv_refresh", first.cookies.get("cv_refresh"), path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_revokes_session(client):
    await signup(client)
    refresh = client.cookies.get("cv_refresh")
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    client.cookies.set("cv_refresh", refresh, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_cross_origin_writes_are_blocked(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.co", "password": "whatever1"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403


async def test_auth_rate_limit(client, monkeypatch):
    # Pin the clock so all attempts land in one fixed window, however slow hashing is.
    import app.core.rate_limit as rl

    monkeypatch.setattr(rl.time, "time", lambda: 1_800_000_000.0)
    statuses = []
    for _ in range(12):
        r = await client.post("/api/v1/auth/login", json={"email": "who@example.com", "password": "wrong-pass-1"})
        statuses.append(r.status_code)
    assert statuses[:10] == [401] * 10
    assert statuses[-1] == 429
