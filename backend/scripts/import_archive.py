"""Bulk-import public-domain feature films from the Internet Archive, streamed directly.

Unlike the curated seed (which downloads and transcodes to HLS), these titles keep their
video on archive.org and the player streams the MP4 straight from there: no storage, no
transcode, so thousands of films can be added in minutes.

Selection (same quality filters as the curated seed):
  * curated collections only (feature_films, silent_films)
  * feature length: 40 min – 4 h, single-part uploads, no trailers/clips/rips/subtitle variants
  * one entry per film: duplicates (same normalised title + year) keep the most-viewed upload

Rights rules:
  --rule date      films dated 1930 or earlier → public domain in the US by date → PUBLISHED
  --rule asserted  uploader-declared Public Domain Mark / CC0 / CC BY / CC BY-SA, dated ≤ 1977
                   → DRAFT (the uploader's claim is not verification; review, then publish).
                   --publish-asserted publishes them anyway (local demos only).
  --rule both      both of the above (default)

Usage:
    npm run import:archive -- --dry-run --limit 50
    npm run import:archive                          # up to 4000 films
"""

import argparse
import asyncio
import html
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
from scripts.seed_public_domain import (
    PREFERRED_FORMATS,
    REJECT,
    REJECT_COLLECTIONS,
    VIDEO_EXT,
    _length_seconds,
    _year_of,
    norm_title,
)

IA = "https://archive.org"
UA = {"User-Agent": "TheatreManiaImporter/1.0 (public-domain catalog)"}
COLLECTIONS = "(collection:feature_films OR collection:silent_films) AND mediatype:movies"
QUERIES = {
    "date": f"{COLLECTIONS} AND year:[1890 TO 1930]",
    # IA's query parser chokes on "/" inside wildcards, so search broadly and filter exactly below.
    "asserted": f"{COLLECTIONS} AND year:[1890 TO 1977] AND licenseurl:*creativecommons*",
}
# Public Domain Mark, CC0, CC BY, CC BY-SA. NonCommercial / NoDerivatives licences are excluded.
ASSERTED_LICENCE = re.compile(r"/publicdomain/(mark|zero)/|/licenses/by(-sa)?/\d", re.IGNORECASE)
FEATURE_MIN_SECONDS = 40 * 60
FEATURE_MAX_SECONDS = 4 * 3600


@dataclass
class Candidate:
    identifier: str
    title: str
    year: int | None
    description: str | None
    file_name: str
    seconds: float
    downloads: int
    licenseurl: str

    @property
    def key(self) -> tuple[str, int | None]:
        return norm_title(self.title), self.year

    @property
    def details_url(self) -> str:
        return f"{IA}/details/{self.identifier}"

    @property
    def playback_url(self) -> str:
        return f"{IA}/download/{self.identifier}/{quote(self.file_name)}"

    @property
    def poster_url(self) -> str:
        return f"{IA}/services/img/{self.identifier}"


def _text(value: object) -> str:
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return str(value or "")


def clean_description(raw: object, limit: int = 1200) -> str | None:
    text = re.sub(r"<[^>]+>", " ", html.unescape(_text(raw)))
    text = " ".join(text.split())
    return (text[: limit - 1] + "…" if len(text) > limit else text) or None


def clean_title(raw: str) -> str:
    title = re.sub(r"\s*[\(\[]\s*(18|19|20)\d{2}\s*[\)\]]\s*$", "", raw.strip())  # trailing "(1925)"
    return title.strip(" -_") or raw.strip()


def pick_feature(identifier: str, data: dict, downloads: int = 0) -> Candidate | None:
    """Pure decision: is this IA item a single, feature-length, non-rip film? (unit-tested)"""
    meta = data.get("metadata") or {}
    title = _text(meta.get("title")).strip()
    if not title or REJECT.search(identifier) or REJECT.search(title):
        return None
    collections = meta.get("collection") or []
    collections = [collections] if isinstance(collections, str) else collections
    if any(c in REJECT_COLLECTIONS for c in collections):
        return None
    files = data.get("files") or []
    originals = [f for f in files if f.get("source") == "original" and f.get("name", "").lower().endswith(VIDEO_EXT)]
    if len(originals) > 1:
        return None  # multi-part or multi-film upload
    videos = []
    for f in files:
        name = f.get("name", "")
        secs = _length_seconds(f.get("length"))
        if (name.lower().endswith(".mp4") and f.get("format") in PREFERRED_FORMATS and not REJECT.search(name)
                and FEATURE_MIN_SECONDS <= secs <= FEATURE_MAX_SECONDS):  # fmt: skip
            videos.append((f, secs))
    if not videos:
        return None
    # Prefer proper h.264 derivatives over low-bitrate 512Kb ones, then the larger file.
    videos.sort(key=lambda fs: (fs[0].get("format") == "512Kb MPEG4", -int(fs[0].get("size") or 0)))
    best, secs = videos[0]
    return Candidate(
        identifier=identifier,
        title=clean_title(title),
        year=_year_of(meta),
        description=clean_description(meta.get("description")),
        file_name=best["name"],
        seconds=secs,
        downloads=downloads,
        licenseurl=_text(meta.get("licenseurl")),
    )


def rights_for(rule: str, cand: Candidate) -> tuple[LicenseType, str]:
    if rule == "date":
        return LicenseType.public_domain, (
            f"Dated {cand.year} on Internet Archive (published 1930 or earlier): US copyright expired. "
            "Verify the print has no newer copyrighted elements (new score, re-release edits)."
        )
    lic = cand.licenseurl.lower()
    if "publicdomain" in lic or "zero" in lic:
        return LicenseType.public_domain, (
            f"Uploader-declared public domain ({cand.licenseurl}) on Internet Archive. NOT independently "
            "verified: confirm copyright status (e.g. non-renewal) before publishing."
        )
    return LicenseType.creative_commons, (
        f"Uploader-declared Creative Commons licence ({cand.licenseurl}) on Internet Archive. Confirm the "
        "uploader holds the rights and keep attribution."
    )


# ----------------------------------------------------------------------------- network


async def scrape(http: httpx.AsyncClient, query: str) -> list[dict]:
    """All matching items via IA's cursor-based scrape API (no 10k paging cap)."""
    items, cursor = [], None
    while True:
        params = {"q": query, "fields": "identifier,title,year,downloads,licenseurl", "count": 5000}
        if cursor:
            params["cursor"] = cursor
        for attempt in range(4):  # IA's search occasionally returns transient 5xx
            resp = await http.get(f"{IA}/services/search/v1/scrape", params=params)
            if resp.status_code < 500:
                break
            await asyncio.sleep(3 * (attempt + 1))
        resp.raise_for_status()
        body = resp.json()
        items.extend(body.get("items", []))
        cursor = body.get("cursor")
        if not cursor:
            return items


async def fetch_metadata(http: httpx.AsyncClient, sem: asyncio.Semaphore, identifier: str) -> dict | None:
    async with sem:
        for attempt in range(3):
            try:
                resp = await http.get(f"{IA}/metadata/{identifier}")
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                return None
            except httpx.HTTPError:
                await asyncio.sleep(1 + attempt)
        return None


# ----------------------------------------------------------------------------- main


async def run(args: argparse.Namespace) -> int:
    rules = ["date", "asserted"] if args.rule == "both" else [args.rule]
    async with SessionLocal() as db:
        existing_ids = {e for e in await db.scalars(select(Movie.external_id).where(Movie.external_id.is_not(None)))}
        existing_keys = {
            (norm_title(m.title), m.release_date.year if m.release_date else None)
            for m in await db.scalars(select(Movie).where(Movie.in_library.is_(True)))
        }
        used_slugs = set(await db.scalars(select(Movie.slug)))

    accepted = rejected = skipped = 0
    published = drafts = 0
    seen_keys = set(existing_keys)

    limits = httpx.Limits(max_connections=args.concurrency + 4)
    async with httpx.AsyncClient(timeout=30, headers=UA, follow_redirects=True, limits=limits) as http:
        sem = asyncio.Semaphore(args.concurrency)
        for rule in rules:
            if accepted >= args.limit:
                break
            print(f"\n== rule '{rule}': searching Internet Archive …", flush=True)
            items = await scrape(http, QUERIES[rule])
            if rule == "asserted":
                items = [it for it in items if ASSERTED_LICENCE.search(str(it.get("licenseurl") or ""))]
            items.sort(key=lambda it: -int(it.get("downloads") or 0))
            print(f"   {len(items)} candidates; checking each for a single feature-length film …", flush=True)

            for start in range(0, len(items), 200):
                if accepted >= args.limit:
                    break
                chunk = [it for it in items[start : start + 200] if f"ia:{it['identifier']}" not in existing_ids]
                skipped += 200 - len(chunk) if start + 200 <= len(items) else len(items) - start - len(chunk)
                metas = await asyncio.gather(*(fetch_metadata(http, sem, it["identifier"]) for it in chunk))
                new_rows = []
                for it, data in zip(chunk, metas, strict=True):
                    cand = pick_feature(it["identifier"], data, int(it.get("downloads") or 0)) if data else None
                    if cand is None:
                        rejected += 1
                        continue
                    if rule == "date" and (cand.year is None or cand.year > 1930):
                        rejected += 1
                        continue
                    if cand.key in seen_keys:
                        skipped += 1  # duplicate upload of a film we already have
                        continue
                    seen_keys.add(cand.key)
                    new_rows.append(cand)
                    if accepted + len(new_rows) >= args.limit:
                        break

                if new_rows and not args.dry_run:
                    async with SessionLocal() as db:
                        for cand in new_rows:
                            publish = rule == "date" or args.publish_asserted
                            lic_type, notes = rights_for(rule, cand)
                            base = catalog.slugify(f"{cand.title} {cand.year or ''}")
                            slug, n = base, 1
                            while slug in used_slugs:
                                n += 1
                                slug = f"{base}-{n}"
                            used_slugs.add(slug)
                            movie = Movie(
                                external_id=f"ia:{cand.identifier}",
                                slug=slug,
                                title=cand.title[:255],
                                overview=cand.description,
                                release_date=catalog.parse_date(f"{cand.year}-01-01") if cand.year else None,
                                runtime=round(cand.seconds / 60),
                                poster_path=cand.poster_url,
                                backdrop_path=cand.poster_url,
                                popularity=float(cand.downloads),
                                in_library=True,
                                status=MovieStatus.published if publish else MovieStatus.draft,
                                published_at=utcnow() if publish else None,
                            )
                            movie.licenses = [License(
                                license_type=lic_type, licensor="Internet Archive (public-domain collection)",
                                source_url=cand.details_url, territories=["US"], notes=notes,
                            )]  # fmt: skip
                            movie.assets = [VideoAsset(
                                status=AssetStatus.ready, progress=100, is_primary=True,
                                source_url=cand.details_url, playback_url=cand.playback_url,
                                duration_seconds=cand.seconds,
                            )]  # fmt: skip
                            db.add(movie)
                        await db.commit()
                elif args.dry_run:
                    for cand in new_rows[:3]:
                        print(f"   • {cand.title} ({cand.year}) {cand.seconds / 60:.0f} min, {cand.downloads} views")

                will_publish = sum(1 for _ in new_rows) if (rule == "date" or args.publish_asserted) else 0
                published += will_publish
                drafts += len(new_rows) - will_publish
                accepted += len(new_rows)
                print(f"   … {accepted} added, {rejected} rejected, {skipped} skipped", flush=True)

    await catalog.invalidate_library_cache()
    verb = "would add" if args.dry_run else "added"
    print(f"\nDone: {verb} {accepted} films ({published} published, {drafts} drafts for review); "
          f"{rejected} rejected by quality/rights filters, {skipped} duplicates or already imported.")  # fmt: skip
    return 0


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rule", choices=["date", "asserted", "both"], default="both")
    parser.add_argument("--limit", type=int, default=4000, help="maximum films to add (default 4000)")
    parser.add_argument("--concurrency", type=int, default=12, help="parallel metadata requests")
    parser.add_argument("--publish-asserted", action="store_true",
                        help="also publish uploader-declared PD/CC titles (local demos only)")
    parser.add_argument("--dry-run", action="store_true", help="evaluate and report, write nothing")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
