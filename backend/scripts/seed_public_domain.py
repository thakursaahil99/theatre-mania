"""Seed the library with 20 public-domain feature films from the Internet Archive.

For each film we:
  1. resolve an Internet Archive item (identifier hint → archive.org advanced search fallback)
     and pick its best H.264/MPEG-4 derivative,
  2. resolve the TMDB id (hint is verified against title/year, else TMDB search),
  3. create a library Movie + public-domain License + VideoAsset(source_url=archive.org),
  4. enqueue the Celery import → FFmpeg → HLS job (skip with --no-transcode).

Titles are created as **drafts** so an admin can check each print before it goes live
(Admin → Library → Publish). Pass --publish to publish immediately (local demos). Even when
published, a title only becomes streamable once its asset is `ready`, because availability
always requires published + active license + ready asset.

Internet Archive matching is deliberately strict: curated collections first, normalised
title similarity ≥ 0.8, release year within ±2, feature length (≥ 10 min), single-part
uploads only, and no release-group rips of commercial restorations (BluRay/BDrip/YTS…).

LEGAL NOTE: The films below are widely documented as public domain in the United States
(pre-1931 releases, or later titles that lacked a copyright notice / were never renewed).
Status differs by country, and restorations or new scores can carry fresh copyrights.
Verify each title for your territories before going live; adjust `territories` if needed.

Usage (inside the backend container):
    python -m scripts.seed_public_domain               # import everything as drafts
    python -m scripts.seed_public_domain --publish     # import and publish (local demo)
    python -m scripts.seed_public_domain --dry-run     # resolve + print, write nothing
    python -m scripts.seed_public_domain --limit 3 --no-transcode
"""

import argparse
import asyncio
import difflib
import re
import sys
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.time import utcnow
from app.models import AssetStatus, License, LicenseType, Movie, MovieStatus, VideoAsset
from app.services import catalog
from app.services.tmdb import TMDBClient, TMDBNotFound

IA = "https://archive.org"
UA = {"User-Agent": "TheatreManiaSeeder/1.0"}
PREFERRED_FORMATS = ("h.264", "h.264 IA", "MPEG4", "512Kb MPEG4")


@dataclass(frozen=True)
class Film:
    title: str
    year: int
    runtime: int  # approximate minutes of the original release; used to pick the right upload
    tmdb_hint: int | None = None
    ia_hint: str | None = None
    pd_basis: str = "Published before 1931; US copyright expired."


NOT_RENEWED = "Copyright not renewed."
NO_NOTICE = "Published without a valid copyright notice."

FILMS: list[Film] = [
    Film("A Trip to the Moon", 1902, 14, 775),
    Film("The Cabinet of Dr. Caligari", 1920, 76, 234),
    Film("Nosferatu", 1922, 94, 653),
    Film("Safety Last!", 1923, 73),
    Film("Sherlock Jr.", 1924, 45, 992),
    Film("Battleship Potemkin", 1925, 75, 643, "BattleshipPotemkin"),
    Film("The Gold Rush", 1925, 95, 962),
    Film("The Phantom of the Opera", 1925, 93, 964, "ThePhantomoftheOpera"),
    Film("The General", 1926, 78, 961, "TheGeneral"),
    Film("Metropolis", 1927, 115, 19),
    Film("His Girl Friday", 1940, 92, 3085, "his_girl_friday", NOT_RENEWED),
    Film("Detour", 1945, 68, ia_hint="Detour", pd_basis=NOT_RENEWED),
    Film("D.O.A.", 1949, 83, pd_basis=NOT_RENEWED),
    Film("Plan 9 from Outer Space", 1957, 79, pd_basis=NOT_RENEWED),
    Film("House on Haunted Hill", 1959, 75, ia_hint="house_on_haunted_hill_ipod", pd_basis=NOT_RENEWED),
    Film("The Little Shop of Horrors", 1960, 72, ia_hint="The_Little_Shop_of_Horrors.mpeg", pd_basis=NOT_RENEWED),
    Film("Carnival of Souls", 1962, 78, ia_hint="CarnivalofSouls", pd_basis=NO_NOTICE),
    Film("Charade", 1963, 113, 4808, pd_basis=NO_NOTICE),
    Film("The Last Man on Earth", 1964, 86, pd_basis=NOT_RENEWED),
    Film("Night of the Living Dead", 1968, 96, 10331, pd_basis=NO_NOTICE),
]


@dataclass
class IAItem:
    identifier: str
    file_name: str
    size: int
    seconds: float = 0.0

    @property
    def details_url(self) -> str:
        return f"{IA}/details/{self.identifier}"

    @property
    def download_url(self) -> str:
        return f"{IA}/download/{self.identifier}/{quote(self.file_name)}"


# ----------------------------------------------------------------------- Internet Archive

# Release-group / rip markers: these are copies of commercial restorations (new scores,
# restored footage), which can carry their own copyright. Also clips, trailers, multi-part
# uploads and subtitle variants, which are not the film itself.
REJECT = re.compile(
    r"yts|yify|rarbg|blu-?ray|bdrip|brrip|web-?dl|x265|hevc|dts-?hd|remux|trailer|\bclip|sample|"
    r"\bpart[\s_-]?\d|\d[\s_-]?of[\s_-]?\d|spanish|subs\b|subtitles",
    re.IGNORECASE,
)
MIN_SECONDS = 600  # anything shorter is a clip, not a feature (A Trip to the Moon is ~14 min)
CURATED = "collection:(feature_films OR silent_films)"
REJECT_COLLECTIONS = ("movie_trailers", "movie_trailers_unsorted")
RUNTIME_TOLERANCE = 0.30  # silent-era transfers run faster/slower depending on frame rate
VIDEO_EXT = (".mp4", ".mpeg", ".mpg", ".avi", ".mkv", ".mov", ".ogv", ".m4v")


def norm_title(text: str) -> str:
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text.lower())
    text = re.sub(r"\b(18|19|20)\d{2}\b", " ", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def title_matches(film: Film, candidate: str) -> bool:
    return difflib.SequenceMatcher(None, norm_title(film.title), norm_title(candidate)).ratio() >= 0.8


def _year_of(meta: dict) -> int | None:
    for key in ("year", "date"):
        m = re.match(r"(\d{4})", str(meta.get(key) or ""))
        if m:
            return int(m.group(1))
    return None


def year_ok(film: Film, meta: dict) -> bool:
    y = _year_of(meta)
    return y is None or abs(y - film.year) <= 2


def _length_seconds(value: object) -> float:
    text = str(value or "")
    try:
        if ":" in text:
            secs = 0.0
            for part in text.split(":"):
                secs = secs * 60 + float(part)
            return secs
        return float(text) if text else 0.0
    except ValueError:
        return 0.0


async def ia_best_file(http: httpx.AsyncClient, identifier: str, film: Film) -> IAItem | None:
    resp = await http.get(f"{IA}/metadata/{identifier}")
    if resp.status_code != 200:
        return None
    data = resp.json()
    meta = data.get("metadata") or {}
    item_title = meta.get("title")
    item_title = " ".join(item_title) if isinstance(item_title, list) else str(item_title or "")
    if REJECT.search(identifier) or REJECT.search(item_title):
        return None
    collections = meta.get("collection") or []
    collections = [collections] if isinstance(collections, str) else collections
    if any(c in REJECT_COLLECTIONS for c in collections):
        return None
    if not title_matches(film, item_title or identifier) or not year_ok(film, meta):
        return None  # e.g. "Kid Sister (1945)" for The Kid, or a 1953 film also called Charade
    files = data.get("files") or []
    originals = [f for f in files if f.get("source") == "original" and f.get("name", "").lower().endswith(VIDEO_EXT)]
    if len(originals) > 1:
        return None  # multi-part or multi-film upload
    videos = [
        f for f in files
        if f.get("name", "").lower().endswith(".mp4")
        and f.get("format") in PREFERRED_FORMATS
        and not REJECT.search(f.get("name", ""))
        and (_length_seconds(f.get("length")) >= MIN_SECONDS
             or (not f.get("length") and int(f.get("size") or 0) >= 40_000_000))
    ]  # fmt: skip
    if not videos:
        return None
    # Prefer proper h.264 derivatives over the low-bitrate 512Kb ones; then the largest file.
    videos.sort(key=lambda f: (f.get("format") == "512Kb MPEG4", -int(f.get("size") or 0)))
    best = videos[0]
    return IAItem(identifier, best["name"], int(best.get("size") or 0), _length_seconds(best.get("length")))


async def ia_search(http: httpx.AsyncClient, film: Film) -> list[str]:
    title = film.title.replace('"', "")
    base = f'title:("{title}") AND mediatype:(movies)'
    years = f"year:[{film.year - 1} TO {film.year + 1}]"
    # Curated public-domain collections first, then progressively looser.
    queries = [f"{base} AND {CURATED} AND {years}", f"{base} AND {CURATED}", f"{base} AND {years}", base]
    found: list[str] = []
    for q in queries:
        resp = await http.get(
            f"{IA}/advancedsearch.php",
            params={"q": q, "fl[]": ["identifier", "title", "licenseurl", "year", "date"], "rows": 15,
                    "sort[]": "downloads desc", "output": "json"},  # fmt: skip
        )
        if resp.status_code != 200:
            continue
        docs = resp.json().get("response", {}).get("docs", [])
        docs.sort(key=lambda d: "publicdomain" not in str(d.get("licenseurl", "")).lower())
        for d in docs:
            if title_matches(film, str(d.get("title", ""))) and year_ok(film, d) and d["identifier"] not in found:
                found.append(d["identifier"])
    return found


def runtime_deviation(film: Film, item: IAItem) -> float:
    """Relative distance from the original runtime (unknown durations rank last)."""
    if not item.seconds:
        return RUNTIME_TOLERANCE
    expected = film.runtime * 60
    return abs(item.seconds - expected) / expected


async def resolve_ia(http: httpx.AsyncClient, film: Film) -> IAItem | None:
    """Evaluate up to 10 candidates and keep the one closest to the original runtime."""
    candidates = ([film.ia_hint] if film.ia_hint else []) + await ia_search(http, film)
    best: tuple[float, int, IAItem] | None = None
    seen: list[str] = []
    for identifier in candidates:
        if identifier in seen:
            continue
        seen.append(identifier)
        if len(seen) > 10:
            break
        item = await ia_best_file(http, identifier, film)
        if item is None:
            continue
        deviation = runtime_deviation(film, item)
        if deviation > RUNTIME_TOLERANCE:
            continue  # wrong cut, a short, or a fragment
        rank = (deviation, len(seen))  # ties -> earlier (curated / hinted) candidate wins
        if best is None or rank < best[:2]:
            best = (*rank, item)
    return best[2] if best else None


# ----------------------------------------------------------------------- TMDB


def _matches(film: Film, data: dict) -> bool:
    title = (data.get("title") or "").lower()
    alt = (data.get("original_title") or "").lower()
    ratio = max(difflib.SequenceMatcher(None, film.title.lower(), t).ratio() for t in (title, alt))
    year = int((data.get("release_date") or "0")[:4] or 0)
    return ratio >= 0.6 and abs(year - film.year) <= 1


async def resolve_tmdb(tmdb: TMDBClient, film: Film) -> dict | None:
    if film.tmdb_hint:
        try:
            data = await tmdb.movie(film.tmdb_hint)
            if _matches(film, data):
                return data
        except TMDBNotFound:
            pass
    hit = await tmdb.search_one(film.title, film.year)
    if hit:
        return await tmdb.movie(hit["id"])
    return None


# ----------------------------------------------------------------------- main


async def seed(args: argparse.Namespace) -> int:
    films = FILMS
    if args.only:
        wanted = [w.strip().lower() for w in args.only.split(",") if w.strip()]
        films = [f for f in films if any(w in f.title.lower() for w in wanted)]
    if args.limit:
        films = films[: args.limit]
    created, skipped, failed = 0, 0, 0
    enqueue = None
    if not args.no_transcode and not args.dry_run:
        from app.workers.tasks import transcode_asset

        enqueue = transcode_asset.delay

    async with TMDBClient.standalone() as tmdb, httpx.AsyncClient(timeout=30, headers=UA, follow_redirects=True) as http:
        if not tmdb.enabled:
            print("! TMDB credentials missing: titles will be created with minimal metadata.", file=sys.stderr)
        for film in films:
            label = f"{film.title} ({film.year})"
            try:
                item = await resolve_ia(http, film)
                if item is None:
                    print(f"✗ {label}: no suitable Internet Archive file found")
                    failed += 1
                    continue
                data = await resolve_tmdb(tmdb, film) if tmdb.enabled else None
                if args.dry_run:
                    print(f"• {label}\n    IA:   {item.download_url} ({item.size / 1e6:.0f} MB, "
                          f"{item.seconds / 60:.0f} min vs ~{film.runtime})\n"
                          f"    TMDB: {data['id'] if data else '—'}")  # fmt: skip
                    continue

                async with SessionLocal() as db:
                    movie = None
                    if data:
                        movie = await db.scalar(select(Movie).where(Movie.tmdb_id == data["id"]))
                    if movie is None:
                        movie = await db.scalar(select(Movie).where(Movie.slug == catalog.slugify(f"{film.title} {film.year}")))
                    if movie is not None and movie.in_library:
                        print(f"→ {label}: already in library, skipping")
                        skipped += 1
                        continue
                    if movie is None:
                        movie = Movie(title=film.title, slug="pending")
                        db.add(movie)
                    if data:
                        await catalog.apply_tmdb_metadata(db, movie, data)
                    else:
                        movie.title = film.title
                        movie.release_date = catalog.parse_date(f"{film.year}-01-01")
                    movie.in_library = True
                    if args.publish:
                        movie.status = MovieStatus.published
                        movie.published_at = utcnow()
                    else:
                        movie.status = MovieStatus.draft
                    movie.slug = await catalog.unique_slug(
                        db, catalog.slugify(f"{movie.title} {film.year}"), exclude_id=movie.id
                    )
                    movie.licenses.append(
                        License(
                            license_type=LicenseType.public_domain,
                            licensor="Public domain (via Internet Archive)",
                            source_url=item.details_url,
                            territories=["US"],
                            notes=film.pd_basis + " Before publishing, confirm this print has no newer copyrighted elements"
                            " (re-release edits, newly composed scores, colorisation). Verify other territories"
                            " before expanding.",
                        )
                    )
                    await db.flush()
                    asset = VideoAsset(movie_id=movie.id, source_url=item.download_url, status=AssetStatus.queued)
                    db.add(asset)
                    await db.commit()
                    if enqueue:
                        result = enqueue(str(asset.id))
                        asset.celery_task_id = result.id
                        await db.commit()
                    created += 1
                    print(f"✓ {label}: tmdb={movie.tmdb_id or '—'} ia={item.identifier}")
            except Exception as exc:  # noqa: BLE001 — keep going on individual failures
                failed += 1
                print(f"✗ {label}: {exc}")

    await catalog.invalidate_library_cache()
    print(f"\nDone. created={created} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


def main() -> None:
    # Windows consoles default to cp1252, which can't print ✓/✗; never crash on output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="resolve sources but write nothing")
    parser.add_argument("--no-transcode", action="store_true", help="create rows but do not enqueue jobs")
    parser.add_argument("--limit", type=int, default=0, help="only process the first N films")
    parser.add_argument("--only", default="", help="comma-separated title substrings to process")
    parser.add_argument("--publish", action="store_true",
                        help="publish immediately (default: draft, for admin review of each print)")
    sys.exit(asyncio.run(seed(parser.parse_args())))


if __name__ == "__main__":
    main()
