from tests.conftest import MISSING_ID


async def test_home_rows_and_hero(client):
    resp = await client.get("/api/v1/movies/home")
    assert resp.status_code == 200
    body = resp.json()
    row_ids = [r["id"] for r in body["rows"]]
    assert row_ids[:5] == ["trending", "bollywood-trending", "bollywood-new", "new", "top_rated"]
    assert "free" not in row_ids  # nothing licensed yet
    assert body["hero"] and body["hero"][0]["trailer"]["key"] == "trailer1"


async def test_home_is_cached(client, tmdb):
    await client.get("/api/v1/movies/home")
    calls = len(tmdb.calls)
    await client.get("/api/v1/movies/home")
    assert len(tmdb.calls) == calls


async def test_detail_for_unlicensed_title_is_metadata_only(client):
    resp = await client.get("/api/v1/movies/10331")
    assert resp.status_code == 200
    d = resp.json()
    assert d["title"] == "Night of the Living Dead"
    assert d["availability"]["streamable"] is False
    assert d["trailer"]["key"] == "trailer1"  # Trailer beats Teaser
    assert d["certification"] == "R"
    assert d["directors"][0]["name"] == "George A. Romero"
    assert d["watch_providers"]["flatrate"][0]["provider_name"] == "Netflix"
    assert len(d["similar"]) == 2


async def test_detail_not_found(client):
    assert (await client.get(f"/api/v1/movies/{MISSING_ID}")).status_code == 404
    assert (await client.get("/api/v1/movies/no-such-slug")).status_code == 404
    assert (await client.get("/api/v1/movies/Bad Key")).status_code in (404, 422)


async def test_search_with_filters(client):
    r = await client.get("/api/v1/search", params={"q": "night"})
    assert [m["title"] for m in r.json()["results"]] == ["Night of the Living Dead"]

    r = await client.get("/api/v1/search", params={"q": "i", "genre": 35})
    assert [m["title"] for m in r.json()["results"]] == ["His Girl Friday"]

    r = await client.get("/api/v1/search", params={"year": 1800})
    assert r.status_code == 422


async def test_trailer_endpoint(client):
    r = await client.get("/api/v1/movies/10331/trailer")
    assert r.json()["trailer"]["key"] == "trailer1"


async def test_play_unlicensed_title_is_forbidden(user_client):
    r = await user_client.post("/api/v1/playback/10331/start")
    assert r.status_code == 403
