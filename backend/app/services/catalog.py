"""Bridges TMDB metadata and our licensed library.

* Normalises TMDB payloads into the public schemas.
* Decides whether a title is streamable (published + active license + ready asset).
* Resolves frontend "movie keys" (TMDB id or slug) to Movie rows, creating catalog stubs
  on demand so watchlists/ratings work for any title.
"""

import json
import re
import unicodedata
import uuid
from datetime import date, datetime
from typing import Any
from urllib.parse import quote_plus

from redis.exceptions import RedisError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.redis import get_redis
from app.core.time import as_aware, utcnow
from app.models import AssetStatus, Genre, License, Movie, MovieStatus, VideoAsset
from app.schemas.movie import (
    Availability,
    CastMember,
    CrewMember,
    ExternalLink,
    GenreOut,
    MovieCard,
    MovieDetail,
    Provider,
    Video,
    WatchProviders,
)
from app.services.tmdb import TMDBClient, TMDBNotFound

LIBRARY_CACHE_KEY = "library:streamable_tmdb_ids:v1"
HOME_CACHE_KEY = "home:v1"
BOLLYWOOD_CACHE_KEY = "bollywood:v1"

# ---------------------------------------------------------------- helpers


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:120] or "title"


def movie_key(movie: Movie) -> str:
    return str(movie.tmdb_id) if movie.tmdb_id else movie.slug


def license_is_active(lic: License, now: datetime | None = None) -> bool:
    now = now or utcnow()
    starts, expires = as_aware(lic.starts_at), as_aware(lic.expires_at)
    return (starts is None or starts <= now) and (expires is None or expires > now)


def active_license(movie: Movie) -> License | None:
    now = utcnow()
    active = [lic for lic in movie.licenses if license_is_active(lic, now)]
    return active[-1] if active else None


def primary_ready_asset(assets: list[VideoAsset]) -> VideoAsset | None:
    ready = [a for a in assets if a.status == AssetStatus.ready]
    ready.sort(key=lambda a: (not a.is_primary, -(as_aware(a.updated_at) or utcnow()).timestamp()))
    return ready[0] if ready else None


def _active_license_clause(now: datetime):
    return and_(
        License.movie_id == Movie.id,
        or_(License.starts_at.is_(None), License.starts_at <= now),
        or_(License.expires_at.is_(None), License.expires_at > now),
    )


def streamable_filter(now: datetime | None = None):
    """SQL predicate: published library title with an active license and a ready asset."""
    now = now or utcnow()
    return and_(
        Movie.in_library.is_(True),
        Movie.status == MovieStatus.published,
        select(License.id).where(_active_license_clause(now)).exists(),
        select(VideoAsset.id)
        .where(VideoAsset.movie_id == Movie.id, VideoAsset.status == AssetStatus.ready)
        .exists(),
    )


async def streamable_tmdb_ids(db: AsyncSession) -> set[int]:
    redis = get_redis()
    try:
        cached = await redis.get(LIBRARY_CACHE_KEY)
        if cached is not None:
            return set(json.loads(cached))
    except RedisError:
        pass
    rows = await db.scalars(select(Movie.tmdb_id).where(streamable_filter(), Movie.tmdb_id.is_not(None)))
    ids = {r for r in rows if r is not None}
    try:
        await redis.set(LIBRARY_CACHE_KEY, json.dumps(sorted(ids)), ex=60)
    except RedisError:
        pass
    return ids


async def invalidate_library_cache() -> None:
    try:
        await get_redis().delete(LIBRARY_CACHE_KEY, HOME_CACHE_KEY, BOLLYWOOD_CACHE_KEY)
    except RedisError:
        pass


# ---------------------------------------------------------------- TMDB → schema


def card_from_tmdb(m: dict[str, Any], streamable_ids: set[int]) -> MovieCard:
    return MovieCard(
        id=str(m["id"]),
        tmdb_id=m["id"],
        title=m.get("title") or m.get("original_title") or "Untitled",
        overview=m.get("overview"),
        poster_path=m.get("poster_path"),
        backdrop_path=m.get("backdrop_path"),
        release_date=m.get("release_date") or None,
        vote_average=m.get("vote_average"),
        genre_ids=m.get("genre_ids") or [g["id"] for g in m.get("genres", [])],
        original_language=m.get("original_language"),
        streamable=m["id"] in streamable_ids,
    )


def cards_from_page(page: dict[str, Any], streamable_ids: set[int], need_poster: bool = True) -> list[MovieCard]:
    return [
        card_from_tmdb(m, streamable_ids)
        for m in page.get("results", [])
        if not need_poster or m.get("poster_path")
    ]


def card_from_movie(movie: Movie, streamable: bool) -> MovieCard:
    return MovieCard(
        id=movie_key(movie),
        tmdb_id=movie.tmdb_id,
        title=movie.title,
        overview=movie.overview,
        poster_path=movie.poster_path,
        backdrop_path=movie.backdrop_path,
        release_date=movie.release_date.isoformat() if movie.release_date else None,
        vote_average=movie.vote_average,
        genre_ids=[g.id for g in movie.genres],
        original_language=movie.original_language,
        streamable=streamable,
    )


def pick_trailer(videos: list[dict[str, Any]]) -> Video | None:
    candidates = [v for v in videos if v.get("site") == "YouTube" and v.get("type") in {"Trailer", "Teaser"}]
    if not candidates:
        return None
    candidates.sort(
        key=lambda v: (
            v.get("type") != "Trailer",
            not v.get("official", False),
            v.get("iso_639_1") != "en",
            -(v.get("size") or 0),
        )
    )
    best = candidates[0]
    return Video(key=best["key"], name=best.get("name", "Trailer"), site="YouTube", type=best.get("type", "Trailer"))


def _videos(data: dict[str, Any]) -> list[Video]:
    out = []
    for v in (data.get("videos") or {}).get("results", []):
        if v.get("site") == "YouTube" and v.get("type") in {"Trailer", "Teaser", "Clip", "Featurette"}:
            out.append(Video(key=v["key"], name=v.get("name", ""), type=v.get("type", "Clip")))
    return out[:12]


def _cast(data: dict[str, Any], limit: int = 20) -> list[CastMember]:
    cast = (data.get("credits") or {}).get("cast", [])
    return [
        CastMember(id=c["id"], name=c["name"], character=c.get("character"), profile_path=c.get("profile_path"))
        for c in sorted(cast, key=lambda c: c.get("order", 999))[:limit]
    ]


def _directors(data: dict[str, Any]) -> list[CrewMember]:
    crew = (data.get("credits") or {}).get("crew", [])
    return [CrewMember(id=c["id"], name=c["name"], job=c["job"]) for c in crew if c.get("job") == "Director"]


def _certification(data: dict[str, Any], region: str) -> str | None:
    for entry in (data.get("release_dates") or {}).get("results", []):
        if entry.get("iso_3166_1") == region:
            for rd in entry.get("release_dates", []):
                if rd.get("certification"):
                    return rd["certification"]
    return None


def _providers(data: dict[str, Any], region: str) -> WatchProviders | None:
    region_data = ((data.get("watch/providers") or {}).get("results") or {}).get(region)
    if not region_data:
        return None

    def conv(items: list[dict[str, Any]] | None) -> list[Provider]:
        return [
            Provider(provider_id=p["provider_id"], provider_name=p["provider_name"], logo_path=p.get("logo_path"))
            for p in sorted(items or [], key=lambda p: p.get("display_priority", 99))
        ]

    return WatchProviders(
        region=region,
        link=region_data.get("link"),
        flatrate=conv(region_data.get("flatrate")),
        rent=conv(region_data.get("rent")),
        buy=conv(region_data.get("buy")),
        free=conv((region_data.get("free") or []) + (region_data.get("ads") or [])),
    )


def external_links(
    title: str, year: str | None, imdb_id: str | None, has_trailer: bool, has_providers: bool, extra: dict | None = None
) -> list[ExternalLink]:
    """Outbound links for titles we can't stream: legal where-to-watch search, trailer search, references."""
    region = settings.TMDB_REGION.lower()
    region = {"gb": "uk"}.get(region, region)
    query = quote_plus(f"{title} {year or ''}".strip())
    links: list[ExternalLink] = []
    if not has_providers:
        links.append(ExternalLink(kind="where_to_watch", label="Find where to watch (JustWatch)",
                                  url=f"https://www.justwatch.com/{region}/search?q={quote_plus(title)}"))  # fmt: skip
    if not has_trailer:
        links.append(ExternalLink(kind="trailer_search", label="Trailer on YouTube",
                                  url=f"https://www.youtube.com/results?search_query={query}+trailer"))  # fmt: skip
    if imdb_id:
        links.append(ExternalLink(kind="imdb", label="IMDb", url=f"https://www.imdb.com/title/{imdb_id}/"))
    extra = extra or {}
    if extra.get("wikipedia"):
        links.append(ExternalLink(kind="wikipedia", label="Wikipedia", url=extra["wikipedia"]))
    if extra.get("wikidata"):
        links.append(ExternalLink(kind="wikidata", label="Wikidata", url=extra["wikidata"]))
    return links


def detail_from_tmdb(
    data: dict[str, Any], availability: Availability, streamable_ids: set[int], region: str
) -> MovieDetail:
    card = card_from_tmdb(data, streamable_ids)
    card.streamable = availability.streamable
    similar_src = (data.get("recommendations") or {}).get("results") or (data.get("similar") or {}).get("results", [])
    return MovieDetail(
        **card.model_dump(),
        tagline=data.get("tagline") or None,
        runtime=data.get("runtime"),
        genres=[GenreOut(id=g["id"], name=g["name"]) for g in data.get("genres", [])],
        certification=_certification(data, region),
        imdb_id=data.get("imdb_id"),
        cast=_cast(data),
        directors=_directors(data),
        trailer=pick_trailer((data.get("videos") or {}).get("results", [])),
        videos=_videos(data),
        similar=[card_from_tmdb(m, streamable_ids) for m in similar_src if m.get("poster_path")][:18],
        watch_providers=(providers := _providers(data, region)),
        links=[] if availability.streamable else external_links(
            card.title, (card.release_date or "")[:4], data.get("imdb_id"),
            has_trailer=bool((data.get("videos") or {}).get("results")), has_providers=providers is not None,
        ),
        availability=availability,
    )


def detail_from_movie(movie: Movie, availability: Availability) -> MovieDetail:
    credits = movie.credits or {}
    return MovieDetail(
        **card_from_movie(movie, availability.streamable).model_dump(),
        tagline=movie.tagline,
        runtime=movie.runtime,
        genres=[GenreOut(id=g.id, name=g.name) for g in movie.genres],
        certification=movie.certification,
        imdb_id=movie.imdb_id,
        cast=[CastMember(**c) for c in credits.get("cast", [])],
        directors=[CrewMember(**c) for c in credits.get("directors", [])],
        trailer=Video(key=movie.trailer_key, name="Trailer") if movie.trailer_key else None,
        links=external_links(
            movie.title, movie.release_date.isoformat()[:4] if movie.release_date else None, movie.imdb_id,
            has_trailer=bool(movie.trailer_key), has_providers=False, extra=credits.get("links"),
        ) if not availability.streamable else [],
        availability=availability,
    )


def movie_fields_from_tmdb(data: dict[str, Any]) -> dict[str, Any]:
    """Column values for a Movie row from a TMDB detail payload."""
    return {
        "tmdb_id": data["id"],
        "imdb_id": data.get("imdb_id"),
        "title": data.get("title") or data.get("original_title") or "Untitled",
        "original_title": data.get("original_title"),
        "overview": data.get("overview"),
        "tagline": data.get("tagline") or None,
        "release_date": parse_date(data.get("release_date")),
        "runtime": data.get("runtime"),
        "original_language": data.get("original_language"),
        "vote_average": data.get("vote_average"),
        "vote_count": data.get("vote_count"),
        "popularity": data.get("popularity"),
        "poster_path": data.get("poster_path"),
        "backdrop_path": data.get("backdrop_path"),
        "trailer_key": (t.key if (t := pick_trailer((data.get("videos") or {}).get("results", []))) else None),
        "certification": _certification(data, settings.TMDB_REGION),
        "credits": {
            "cast": [c.model_dump() for c in _cast(data, 15)],
            "directors": [c.model_dump() for c in _directors(data)],
        },
    }


def genre_pairs(data: dict[str, Any]) -> list[tuple[int, str]]:
    return [(g["id"], g["name"]) for g in data.get("genres", [])]


async def upsert_genres(db: AsyncSession, pairs: list[tuple[int, str]]) -> list[Genre]:
    if not pairs:
        return []
    existing = {g.id: g for g in await db.scalars(select(Genre).where(Genre.id.in_([p[0] for p in pairs])))}
    out = []
    for gid, name in pairs:
        genre = existing.get(gid)
        if genre is None:
            genre = Genre(id=gid, name=name)
            db.add(genre)
        out.append(genre)
    return out


async def unique_slug(db: AsyncSession, base: str, exclude_id: uuid.UUID | None = None) -> str:
    slug, n = base, 1
    while True:
        stmt = select(Movie.id).where(Movie.slug == slug)
        if exclude_id:
            stmt = stmt.where(Movie.id != exclude_id)
        if (await db.scalar(stmt)) is None:
            return slug
        n += 1
        slug = f"{base}-{n}"


async def apply_tmdb_metadata(db: AsyncSession, movie: Movie, data: dict[str, Any]) -> None:
    for field, value in movie_fields_from_tmdb(data).items():
        setattr(movie, field, value)
    movie.genres = await upsert_genres(db, genre_pairs(data))
    movie.metadata_synced_at = utcnow()


# ---------------------------------------------------------------- lookups


async def get_movie_by_key(db: AsyncSession, key: str, with_assets: bool = False) -> Movie | None:
    stmt = select(Movie)
    stmt = stmt.where(Movie.tmdb_id == int(key)) if key.isdigit() else stmt.where(Movie.slug == key)
    if with_assets:
        stmt = stmt.options(selectinload(Movie.assets))
    return await db.scalar(stmt)


async def availability_for(db: AsyncSession, movie: Movie | None) -> tuple[Availability, VideoAsset | None]:
    if movie is None or not movie.in_library or movie.status != MovieStatus.published:
        return Availability(streamable=False), None
    lic = active_license(movie)
    assets = list(
        await db.scalars(select(VideoAsset).where(VideoAsset.movie_id == movie.id, VideoAsset.status == AssetStatus.ready))
    )
    asset = primary_ready_asset(assets)
    if lic is None or asset is None:
        return Availability(streamable=False), None
    return (
        Availability(
            streamable=True,
            license_type=lic.license_type.value,
            expires_at=lic.expires_at,
            duration_seconds=asset.duration_seconds,
            has_subtitles=bool(asset.subtitles),
        ),
        asset,
    )


async def ensure_movie(db: AsyncSession, tmdb: TMDBClient, key: str) -> Movie:
    """Resolve a movie key to a row, creating a TMDB catalog stub if necessary."""
    movie = await get_movie_by_key(db, key)
    if movie is not None:
        return movie
    if not key.isdigit():
        raise LookupError(key)
    try:
        data = await tmdb.movie(int(key))
    except TMDBNotFound as exc:
        raise LookupError(key) from exc
    fields = movie_fields_from_tmdb(data)
    year = fields["release_date"].year if fields["release_date"] else ""
    movie = Movie(**fields, slug=f"{slugify(fields['title'])}-{year}-{data['id']}".replace("--", "-"), in_library=False)
    movie.genres = await upsert_genres(db, genre_pairs(data))
    movie.metadata_synced_at = utcnow()
    db.add(movie)
    await db.flush()
    return movie
