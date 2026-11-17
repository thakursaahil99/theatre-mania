from datetime import date

from app.services import bollywood


async def test_bollywood_hub_rows_and_hero(client, tmdb):
    resp = await client.get("/api/v1/movies/bollywood")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body["rows"]] == [f"bollywood-{slug}" for slug, _ in bollywood.ROWS]
    assert body["rows"][0]["title"] == "Trending in Bollywood"
    assert body["rows"][0]["href"] == "/browse/bollywood-trending"
    assert body["rows"][0]["items"][0]["title"] == "Dilwale Dulhania Le Jayenge"
    assert body["hero"] and body["hero"][0]["trailer"]["key"] == "trailer1"

    discover = [p for path, p in tmdb.requests if path == "/discover/movie"]
    assert len(discover) == len(bollywood.ROWS)
    assert all(p["with_original_language"] == "hi" and p["region"] == "IN" for p in discover)


async def test_bollywood_hub_is_cached(client, tmdb):
    await client.get("/api/v1/movies/bollywood")
    calls = len(tmdb.calls)
    await client.get("/api/v1/movies/bollywood")
    assert len(tmdb.calls) == calls


async def test_bollywood_see_all_lists(client, tmdb):
    r = await client.get("/api/v1/movies/list/bollywood-top", params={"page": 2})
    assert r.status_code == 200
    assert r.json()["total_pages"] == 3
    path, params = tmdb.requests[-1]
    assert path == "/discover/movie"
    assert params["sort_by"] == "vote_average.desc" and params["vote_count.gte"] == 300 and params["page"] == 2

    assert (await client.get("/api/v1/movies/list/bollywood-nope")).status_code == 404
    assert (await client.get("/api/v1/movies/list/bollywood-")).status_code == 422


def test_row_filters():
    today = date(2026, 11, 17)
    new = bollywood.filters("new", today)
    assert new["primary_release_date.gte"] == "2026-05-21" and new["primary_release_date.lte"] == "2026-11-17"
    assert bollywood.filters("thriller")["with_genres"] == "53|80"  # thriller OR crime
    assert bollywood.filters("classics")["primary_release_date.lte"] == "1989-12-31"
    assert bollywood.filters("unknown") is None
    assert set(bollywood.HOME_ROWS) <= set(bollywood.TITLES)
