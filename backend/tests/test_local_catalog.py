"""Bollywood without a TMDB key: rows, lists, detail pages and search from the Wikidata catalog."""

from datetime import date, timedelta

import pytest

from app.models import Genre, Movie


@pytest.fixture
async def bollywood_catalog(session_factory, tmdb):
    tmdb.is_enabled = False
    today = date.today()
    async with session_factory() as db:
        romance, action = Genre(id=10749, name="Romance"), Genre(id=28, name="Action")
        rows = [
            ("Dilwale Dulhania Le Jayenge", date(1995, 10, 20), 90, [romance], "tt0112870"),
            ("Sholay", date(1975, 8, 15), 95, [action], "tt0073707"),
            ("A New Hit", today - timedelta(days=40), 40, [action], None),
            ("Mughal-e-Azam", date(1960, 8, 5), 70, [romance], None),
        ]
        for i, (title, released, pop, genres, imdb) in enumerate(rows):
            m = Movie(
                external_id=f"wd:Q{100 + i}", slug=f"film-{i}", title=title, release_date=released, popularity=pop,
                original_language="hi", imdb_id=imdb, in_library=False,
                credits={"cast": [{"id": 1, "name": "Shah Rukh Khan", "character": None, "profile_path": None}],
                         "directors": [{"id": 2, "name": "Aditya Chopra", "job": "Director"}],
                         "links": {"wikipedia": "https://en.wikipedia.org/wiki/X", "wikidata": f"https://www.wikidata.org/wiki/Q{100 + i}"}},
            )  # fmt: skip
            m.genres = genres
            db.add(m)
        await db.commit()


async def test_hub_rows_from_local_catalog(client, bollywood_catalog):
    body = (await client.get("/api/v1/movies/bollywood")).json()
    rows = {r["id"]: [m["title"] for m in r["items"]] for r in body["rows"]}
    assert rows["bollywood-trending"] == ["A New Hit"]  # released in the last 3 years
    assert rows["bollywood-top"][0] == "Sholay"  # most notable first
    assert rows["bollywood-romance"] == ["Dilwale Dulhania Le Jayenge", "Mughal-e-Azam"]
    assert rows["bollywood-classics"] == ["Sholay", "Mughal-e-Azam"]  # released 1989 or earlier only
    assert "bollywood-family" not in rows  # empty rows are omitted


async def test_home_and_see_all_lists_use_local_catalog(client, bollywood_catalog):
    home = (await client.get("/api/v1/movies/home")).json()
    assert any(r["id"] == "bollywood-new" and r["items"][0]["title"] == "A New Hit" for r in home["rows"])
    page = (await client.get("/api/v1/movies/list/bollywood-action")).json()
    assert [m["title"] for m in page["results"]] == ["Sholay", "A New Hit"]
    assert page["total_results"] == 2


async def test_catalog_detail_has_links_and_similar(client, bollywood_catalog):
    d = (await client.get("/api/v1/movies/film-0")).json()
    assert d["title"] == "Dilwale Dulhania Le Jayenge"
    assert d["availability"]["streamable"] is False
    assert d["directors"][0]["name"] == "Aditya Chopra" and d["cast"][0]["name"] == "Shah Rukh Khan"
    kinds = {link["kind"]: link["url"] for link in d["links"]}
    assert kinds["where_to_watch"].startswith("https://www.justwatch.com/")
    assert "youtube.com/results" in kinds["trailer_search"]
    assert kinds["imdb"] == "https://www.imdb.com/title/tt0112870/"
    assert set(kinds) >= {"wikipedia", "wikidata"}
    assert [m["title"] for m in d["similar"]] == ["Mughal-e-Azam"]  # same genre


async def test_local_search_without_tmdb(client, bollywood_catalog):
    r = (await client.get("/api/v1/search", params={"q": "sholay"})).json()
    assert [m["title"] for m in r["results"]] == ["Sholay"]
    r = (await client.get("/api/v1/search", params={"language": "hi", "genre": 10749})).json()
    assert [m["title"] for m in r["results"]] == ["Dilwale Dulhania Le Jayenge", "Mughal-e-Azam"]


async def test_watchlist_works_for_catalog_entries(user_client, bollywood_catalog):
    assert (await user_client.put("/api/v1/me/watchlist/film-1")).status_code == 204
    assert [m["title"] for m in (await user_client.get("/api/v1/me/watchlist")).json()] == ["Sholay"]
