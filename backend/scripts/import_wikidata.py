"""Import the Bollywood (Hindi-language) film catalog from Wikidata: no API key needed.

Wikidata is CC0 open data. Overviews come from English Wikipedia's article intros (CC BY-SA,
attributed on each title page). Only *freely licensed* Wikipedia images are used as posters,
so most films show a designed title card until a TMDB key adds official artwork.

These are catalog entries (metadata only, like TMDB titles): they are never streamable unless
a licensed video is added through the admin studio.

Usage:
    npm run import:bollywood -- --dry-run
    npm run import:bollywood                  # all ~8,000 Hindi films
"""

import argparse
import asyncio
import re
import sys
from datetime import date

import httpx
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Genre, Movie
from app.services import catalog

SPARQL = "https://query.wikidata.org/sparql"
WIKI_API = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "TheatreManiaCatalog/1.0 (open-data film catalog import)"}
HINDI_FILMS = "?f wdt:P31 wd:Q11424; wdt:P364 wd:Q1568."

# Wikidata genre item → TMDB genre ids (the genre vocabulary the rest of the app uses).
GENRE_MAP: dict[str, tuple[int, ...]] = {
    "Q188473": (28,),  # action film
    "Q157443": (35,),  # comedy film
    "Q130232": (18,),  # drama film
    "Q1054574": (10749,),  # romance film
    "Q860626": (10749, 35),  # romantic comedy
    "Q2484376": (53,),  # thriller film
    "Q959790": (80,),  # crime film
    "Q200092": (27,),  # horror film
    "Q842256": (10402,),  # musical film
    "Q471839": (878,),  # science fiction film
    "Q202866": (16,),  # animated film
    "Q93204": (99,),  # documentary film
    "Q369747": (10752,),  # war film
    "Q645928": (18,),  # biographical film
    "Q17013749": (36,),  # historical film
    "Q157394": (14,),  # fantasy film
}
GENRE_NAMES = {28: "Action", 35: "Comedy", 18: "Drama", 10749: "Romance", 53: "Thriller", 80: "Crime",
               27: "Horror", 10402: "Music", 878: "Science Fiction", 16: "Animation", 99: "Documentary",
               10752: "War", 36: "History", 14: "Fantasy"}  # fmt: skip
QID = re.compile(r"Q\d+$")


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


async def sparql(http: httpx.AsyncClient, body: str) -> list[dict]:
    for attempt in range(4):
        resp = await http.get(SPARQL, params={"query": body}, headers={"Accept": "application/sparql-results+json"})
        if resp.status_code == 200:
            return resp.json()["results"]["bindings"]
        await asyncio.sleep(5 * (attempt + 1))  # 429 / 5xx: back off
    resp.raise_for_status()
    return []


async def fetch_catalog(http: httpx.AsyncClient) -> dict[str, dict]:
    label = 'SERVICE wikibase:label { bd:serviceParam wikibase:language "en,hi". }'
    base, genres, directors, cast = await asyncio.gather(
        sparql(http, f"""SELECT ?f ?fLabel ?date ?imdb ?dur ?wp ?links WHERE {{ {HINDI_FILMS}
            ?f wikibase:sitelinks ?links.
            OPTIONAL {{ ?f wdt:P577 ?date }} OPTIONAL {{ ?f wdt:P345 ?imdb }} OPTIONAL {{ ?f wdt:P2047 ?dur }}
            OPTIONAL {{ ?wp schema:about ?f; schema:isPartOf <https://en.wikipedia.org/> }} {label} }}"""),
        sparql(http, f"SELECT ?f ?g WHERE {{ {HINDI_FILMS} ?f wdt:P136 ?g }}"),
        sparql(http, f"SELECT ?f ?d ?dLabel WHERE {{ {HINDI_FILMS} ?f wdt:P57 ?d. {label} }}"),
        sparql(http, f"SELECT ?f ?c ?cLabel WHERE {{ {HINDI_FILMS} ?f wdt:P161 ?c. {label} }}"),
    )  # fmt: skip
    films: dict[str, dict] = {}
    for row in base:
        q = qid(row["f"]["value"])
        title = row.get("fLabel", {}).get("value", "")
        if not title or QID.match(title):
            continue  # no English/Hindi label
        f = films.setdefault(q, {"title": title, "dates": set(), "genres": set(), "directors": {}, "cast": {}})
        if "date" in row:
            f["dates"].add(row["date"]["value"][:10])
        if "imdb" in row and row["imdb"]["value"].startswith("tt"):
            f["imdb"] = row["imdb"]["value"]
        if "dur" in row:
            try:
                f["runtime"] = round(float(row["dur"]["value"]))
            except ValueError:
                pass
        if "wp" in row:
            f["wikipedia"] = row["wp"]["value"]
        f["links"] = int(row["links"]["value"])
    for row in genres:
        if (f := films.get(qid(row["f"]["value"]))) is not None:
            f["genres"].update(GENRE_MAP.get(qid(row["g"]["value"]), ()))
    for rows, key, var in ((directors, "directors", "d"), (cast, "cast", "c")):
        for row in rows:
            f = films.get(qid(row["f"]["value"]))
            name = row.get(f"{var}Label", {}).get("value", "")
            if f is not None and name and not QID.match(name):
                f[key][qid(row[var]["value"])] = name
    return films


def wiki_title(url: str) -> str:
    return httpx.URL(url).path.removeprefix("/wiki/").replace("_", " ")


async def fetch_summaries(http: httpx.AsyncClient, titles: list[str], concurrency: int = 4) -> dict[str, dict]:
    """Intro extracts + FREE lead images for up to 20 articles per request."""
    out: dict[str, dict] = {}
    sem = asyncio.Semaphore(concurrency)

    async def batch(chunk: list[str]) -> None:
        params = {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
                  "prop": "extracts|pageimages", "exintro": "1", "explaintext": "1", "exlimit": "20",
                  "piprop": "thumbnail", "pithumbsize": "500", "pilicense": "free", "titles": "|".join(chunk)}  # fmt: skip
        async with sem:
            for attempt in range(3):
                try:
                    resp = await http.get(WIKI_API, params=params)
                    if resp.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(2 * (attempt + 1))
            else:
                return
        q = resp.json().get("query", {})
        alias = {n["to"]: n["from"] for n in q.get("normalized", []) + q.get("redirects", [])}
        for page in q.get("pages", []):
            original = alias.get(page.get("title"), page.get("title"))
            out[original] = {"extract": page.get("extract"), "image": (page.get("thumbnail") or {}).get("source")}

    await asyncio.gather(*(batch(titles[i : i + 20]) for i in range(0, len(titles), 20)))
    return out


def overview(extract: str | None, limit: int = 700) -> str | None:
    if not extract:
        return None
    text = " ".join(extract.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(". ", 1)[0]
    return (cut if len(cut) > 200 else text[:limit].rsplit(" ", 1)[0]) + "…"


async def run(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient(timeout=90, headers=UA, follow_redirects=True) as http:
        print("Querying Wikidata for Hindi-language films …", flush=True)
        films = await fetch_catalog(http)
        print(f"  {len(films)} films with titles", flush=True)
        titles = [wiki_title(f["wikipedia"]) for f in films.values() if f.get("wikipedia")]
        print(f"Fetching {len(titles)} Wikipedia summaries …", flush=True)
        summaries = await fetch_summaries(http, titles)

    today = date.today()
    added = skipped = 0
    async with SessionLocal() as db:
        existing = set(await db.scalars(select(Movie.external_id).where(Movie.external_id.like("wd:%"))))
        used_slugs = set(await db.scalars(select(Movie.slug)))
        genre_rows = {g.id: g for g in await db.scalars(select(Genre))}
        for gid, name in GENRE_NAMES.items():
            if gid not in genre_rows:
                genre_rows[gid] = Genre(id=gid, name=name)
                db.add(genre_rows[gid])

        for q, f in sorted(films.items(), key=lambda kv: -kv[1].get("links", 0)):
            if f"wd:{q}" in existing:
                skipped += 1
                continue
            released = min((catalog.parse_date(d) for d in f["dates"] if catalog.parse_date(d)), default=None)
            if released and released.year > today.year + 1:
                continue  # announced, not released
            wp_title = wiki_title(f["wikipedia"]) if f.get("wikipedia") else None
            summary = summaries.get(wp_title or "", {})
            year = released.year if released else ""
            base = catalog.slugify(f"{f['title']} {year}")
            slug, n = base, 1
            while slug in used_slugs:
                n += 1
                slug = f"{base}-{n}"
            used_slugs.add(slug)
            runtime = f.get("runtime") if f.get("runtime") and 20 <= f["runtime"] <= 300 else None
            movie = Movie(
                external_id=f"wd:{q}",
                slug=slug,
                title=f["title"][:255],
                imdb_id=f.get("imdb"),
                overview=overview(summary.get("extract")),
                release_date=released,
                runtime=runtime,
                original_language="hi",
                poster_path=summary.get("image"),
                popularity=float(f.get("links", 0)),
                in_library=False,
                credits={
                    "cast": [{"id": int(k[1:]), "name": v, "character": None, "profile_path": None}
                             for k, v in list(f["cast"].items())[:10]],
                    "directors": [{"id": int(k[1:]), "name": v, "job": "Director"} for k, v in f["directors"].items()],
                    "links": {"wikidata": f"https://www.wikidata.org/wiki/{q}",
                              **({"wikipedia": f["wikipedia"]} if f.get("wikipedia") else {})},
                },  # fmt: skip
            )
            movie.genres = [genre_rows[g] for g in sorted(f["genres"]) if g in genre_rows]
            added += 1
            if not args.dry_run:
                db.add(movie)
                if added % 500 == 0:
                    await db.commit()
                    print(f"  … {added} saved", flush=True)
        if not args.dry_run:
            await db.commit()

    await catalog.invalidate_library_cache()
    with_poster = sum(1 for s in summaries.values() if s.get("image"))
    print(f"\nDone: {'would add' if args.dry_run else 'added'} {added} Bollywood titles "
          f"({len(summaries)} with Wikipedia overviews, {with_poster} with free images); {skipped} already present.")  # fmt: skip
    return 0


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
