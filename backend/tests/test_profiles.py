async def test_profile_limit_and_crud(user_client):
    c = user_client
    for name in ("Kids", "Sam", "Alex"):
        r = await c.post("/api/v1/profiles", json={"name": name, "avatar": "ember", "is_kids": name == "Kids"})
        assert r.status_code == 201, r.text
    fifth = await c.post("/api/v1/profiles", json={"name": "Extra"})
    assert fifth.status_code == 409

    profiles = (await c.get("/api/v1/profiles")).json()
    assert len(profiles) == 4
    sam = next(p for p in profiles if p["name"] == "Sam")

    r = await c.patch(f"/api/v1/profiles/{sam['id']}", json={"avatar": "aurora"})
    assert r.json()["avatar"] == "aurora"
    assert (await c.patch(f"/api/v1/profiles/{sam['id']}", json={"avatar": "not-an-avatar"})).status_code == 422

    sel = await c.post(f"/api/v1/profiles/{sam['id']}/select")
    assert sel.status_code == 200
    assert c.cookies.get("cv_profile") == sam["id"]

    assert (await c.delete(f"/api/v1/profiles/{sam['id']}")).status_code == 204


async def test_cannot_delete_last_profile(user_client):
    only = (await user_client.get("/api/v1/profiles")).json()[0]
    assert (await user_client.delete(f"/api/v1/profiles/{only['id']}")).status_code == 409


async def test_duplicate_profile_names(user_client):
    await user_client.post("/api/v1/profiles", json={"name": "Sam"})
    assert (await user_client.post("/api/v1/profiles", json={"name": "Sam"})).status_code == 409
