import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, TMDB
from app.core.config import settings
from app.core.rate_limit import search_limiter
from app.core.redis import get_redis
from app.models import Genre, Movie
from app.schemas.movie import GenreOut, HomeOut, MovieCard, MovieDetail, MoviePage, MovieRow, TrailerOut
from app.services import bollywood, catalog
from app.services.tmdb import EMPTY_PAGE, TMDBClient, TMDBError, TMDBNotFound

log = logging.getLogger(__name__)
router = APIRouter(tags=["catalog"])

MOVIE_KEY = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,159}$", description="TMDB id or library slug")
HOME_CACHE_KEY = catalog.HOME_CACHE_KEY
BOLLYWOOD_CACHE_KEY = catalog.BOLLYWOOD_CACHE_KEY
GENRE_ROWS: list[tuple[int, str]] = [
    (28, "Pulse-Pounding Action"),
    (878, "Sci-Fi Worlds"),
    (35, "Comedy Night"),
    (27, "After Dark: Horror"),
    (18, "Acclaimed Dramas"),
    (16, "Animated Adventures"),
]
LIST_KINDS = {"trending", "new", "top_rated", "popular", "free"}


async def _safe(coro) -> dict[str, Any]:
    try:
        return await coro
    except TMDBError:
        log.warning("TMDB call failed", exc_info=True)
        return EMPTY_PAGE


async def free_to_watch(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[list[Movie], int]:
    base = select(Movie).where(catalog.streamable_filter())
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = await db.scalars(
        # Hand-curated / uploaded titles first, then bulk imports by popularity (IA view counts).
        base.order_by(
            Movie.external_id.is_(None).desc(),
            Movie.popularity.desc().nulls_last(),
            Movie.published_at.desc().nulls_last(),
            Movie.title,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def local_bollywood(db: AsyncSession, slug: str, page: int = 1, page_size: int = 24) -> tuple[list[MovieCard], int]:
    """A Bollywood row from the local (Wikidata-imported) catalog, for when TMDB isn't configured."""
    stmt = bollywood.local_query(slug)
    if stmt is None:
        return [], 0
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    movies = list(await db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return await cards_for_movies(db, movies), total


async def _hero(
    tmdb: TMDBClient, trending: dict[str, Any], streamable: set[int], db: AsyncSession, library_fallback: bool = True
) -> list[MovieDetail]:
    candidates = [m for m in trending.get("results", []) if m.get("backdrop_path")][:5]
    details = await asyncio.gather(*(tmdb.movie(m["id"]) for m in candidates), return_exceptions=True)
    hero: list[MovieDetail] = []
    for data in details:
        if isinstance(data, Exception):
            continue
        availability = catalog.Availability(streamable=data["id"] in streamable)
        detail = catalog.detail_from_tmdb(data, availability, streamable, settings.TMDB_REGION)
        # Hero only needs lightweight fields; drop heavy lists to keep the payload small.
        detail.similar, detail.cast, detail.videos = [], detail.cast[:3], []
        hero.append(detail)
    if not hero and library_fallback:
        # TMDB unavailable: fall back to our own library.
        movies, _ = await free_to_watch(db, 1, 5)
        hero = [
            catalog.detail_from_movie(m, catalog.Availability(streamable=True)) for m in movies if m.backdrop_path
        ]
    return hero


@router.get("/movies/home", response_model=HomeOut)
async def home(db: DB, tmdb: TMDB) -> HomeOut:
    redis = get_redis()
    try:
        if cached := await redis.get(HOME_CACHE_KEY):
            return HomeOut.model_validate_json(cached)
    except RedisError:
        pass

    streamable = await catalog.streamable_tmdb_ids(db)
    trending, new, top, *rest = await asyncio.gather(
        _safe(tmdb.trending()),
        _safe(tmdb.now_playing()),
        _safe(tmdb.top_rated()),
        *(_safe(tmdb.discover(**bollywood.filters(slug))) for slug in bollywood.HOME_ROWS),
        *(_safe(tmdb.discover(with_genres=gid, **{"vote_count.gte": 200})) for gid, _ in GENRE_ROWS),
    )
    bolly_pages, genre_pages = rest[: len(bollywood.HOME_ROWS)], rest[len(bollywood.HOME_ROWS) :]
    free, _ = await free_to_watch(db, 1, 24)

    rows: list[MovieRow] = []
    if items := catalog.cards_from_page(trending, streamable):
        rows.append(MovieRow(id="trending", title="Trending This Week", items=items, href="/browse/trending"))
    if free:
        rows.append(
            MovieRow(
                id="free",
                title="Free to Watch — Stream Now",
                items=[catalog.card_from_movie(m, True) for m in free],
                href="/browse/free",
            )
        )
    for slug, page in zip(bollywood.HOME_ROWS, bolly_pages, strict=True):
        items = catalog.cards_from_page(page, streamable) if tmdb.enabled else (await local_bollywood(db, slug))[0]
        if items:
            rows.append(MovieRow(id=f"bollywood-{slug}", title=bollywood.TITLES[slug], items=items,
                                 href=f"/browse/bollywood-{slug}"))  # fmt: skip
    if items := catalog.cards_from_page(new, streamable):
        rows.append(MovieRow(id="new", title="New Releases", items=items, href="/browse/new"))
    if items := catalog.cards_from_page(top, streamable):
        rows.append(MovieRow(id="top_rated", title="Top Rated of All Time", items=items, href="/browse/top_rated"))
    for (gid, title), page in zip(GENRE_ROWS, genre_pages, strict=True):
        if items := catalog.cards_from_page(page, streamable):
            rows.append(MovieRow(id=f"genre-{gid}", title=title, items=items, href=f"/browse/genre-{gid}"))

    out = HomeOut(hero=await _hero(tmdb, trending, streamable, db), rows=rows)
    try:
        await redis.set(HOME_CACHE_KEY, out.model_dump_json(), ex=settings.HOME_CACHE_TTL)
    except RedisError:
        pass
    return out


@router.get("/movies/bollywood", response_model=HomeOut)
async def bollywood_hub(db: DB, tmdb: TMDB) -> HomeOut:
    """Hindi-language cinema: curated rows + trailer hero (metadata, trailers, Indian providers)."""
    redis = get_redis()
    try:
        if cached := await redis.get(BOLLYWOOD_CACHE_KEY):
            return HomeOut.model_validate_json(cached)
    except RedisError:
        pass

    streamable = await catalog.streamable_tmdb_ids(db)
    if tmdb.enabled:
        pages = await asyncio.gather(*(_safe(tmdb.discover(**bollywood.filters(slug))) for slug, _ in bollywood.ROWS))
        row_items = [catalog.cards_from_page(page, streamable) for page in pages]
        hero = await _hero(tmdb, pages[0], streamable, db, library_fallback=False)
    else:  # no TMDB key: serve the Wikidata-imported catalog
        row_items = [(await local_bollywood(db, slug))[0] for slug, _ in bollywood.ROWS]
        hero = []
    rows = [
        MovieRow(id=f"bollywood-{slug}", title=title, items=items, href=f"/browse/bollywood-{slug}")
        for (slug, title), items in zip(bollywood.ROWS, row_items, strict=True)
        if items
    ]
    out = HomeOut(hero=hero, rows=rows)
    try:
        await redis.set(BOLLYWOOD_CACHE_KEY, out.model_dump_json(), ex=settings.HOME_CACHE_TTL)
    except RedisError:
        pass
    return out


@router.get("/movies/genres", response_model=list[GenreOut])
async def genres(tmdb: TMDB) -> list[GenreOut]:
    try:
        return [GenreOut(**g) for g in await tmdb.genres()]
    except TMDBError:
        return []


@router.get("/movies/list/{kind}", response_model=MoviePage)
async def list_movies(
    db: DB,
    tmdb: TMDB,
    kind: str = Path(pattern=r"^(trending|new|top_rated|popular|free|genre-\d{1,6}|bollywood-[a-z]{2,20})$"),
    page: int = Query(1, ge=1, le=500),
) -> MoviePage:
    if kind == "free":
        movies, total = await free_to_watch(db, page, 40)
        return MoviePage(
            page=page,
            total_pages=max(1, -(-total // 40)),
            total_results=total,
            results=[catalog.card_from_movie(m, True) for m in movies],
        )
    row_filters = None
    if kind.startswith("bollywood-"):
        row_filters = bollywood.filters(kind.removeprefix("bollywood-"))
        if row_filters is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown list")
        if not tmdb.enabled:
            cards, total = await local_bollywood(db, kind.removeprefix("bollywood-"), page, 40)
            return MoviePage(page=page, total_pages=max(1, -(-total // 40)), total_results=total, results=cards)
    fetch = {
        "trending": lambda: tmdb.trending(page=page),
        "new": lambda: tmdb.now_playing(page=page),
        "top_rated": lambda: tmdb.top_rated(page=page),
        "popular": lambda: tmdb.popular(page=page),
    }.get(kind) or (
        (lambda: tmdb.discover(page=page, **row_filters))
        if row_filters is not None
        else (lambda: tmdb.discover(page=page, with_genres=int(kind.split("-")[1])))
    )
    data = await _safe(fetch())
    streamable = await catalog.streamable_tmdb_ids(db)
    return MoviePage(
        page=data.get("page", page),
        total_pages=min(data.get("total_pages", 0), 500),
        total_results=data.get("total_results", 0),
        results=catalog.cards_from_page(data, streamable),
    )


@router.get("/search", response_model=MoviePage, dependencies=[Depends(search_limiter)])
async def search(
    db: DB,
    tmdb: TMDB,
    q: str | None = Query(None, max_length=100),
    genre: int | None = Query(None, ge=1),
    year: int | None = Query(None, ge=1874, le=2100),
    language: str | None = Query(None, pattern=r"^[a-z]{2}$"),
    min_rating: float | None = Query(None, ge=0, le=10),
    free_only: bool = False,
    page: int = Query(1, ge=1, le=500),
) -> MoviePage:
    q = (q or "").strip() or None
    streamable = await catalog.streamable_tmdb_ids(db)

    if not tmdb.enabled and not free_only:
        return await local_search(db, q, genre, year, language, min_rating, page)

    if free_only:
        stmt = select(Movie).where(catalog.streamable_filter())
        if q:
            stmt = stmt.where(Movie.title.ilike(f"%{q.replace('%', '').replace('_', '')}%"))
        if year:
            stmt = stmt.where(func.extract("year", Movie.release_date) == year)
        if language:
            stmt = stmt.where(Movie.original_language == language)
        if min_rating is not None:
            stmt = stmt.where(Movie.vote_average >= min_rating)
        movies = [m for m in await db.scalars(stmt.order_by(Movie.title).limit(200))]
        if genre:
            movies = [m for m in movies if any(g.id == genre for g in m.genres)]
        return MoviePage(
            page=1, total_pages=1, total_results=len(movies), results=[catalog.card_from_movie(m, True) for m in movies]
        )

    if q:
        data = await _safe(tmdb.search(q, page=page, year=year))
        results = catalog.cards_from_page(data, streamable, need_poster=False)
        # TMDB search can't filter by genre/language/rating, so apply those here.
        if genre:
            results = [r for r in results if genre in r.genre_ids]
        if language:
            results = [r for r in results if r.original_language == language]
        if min_rating is not None:
            results = [r for r in results if (r.vote_average or 0) >= min_rating]
    else:
        filters: dict[str, Any] = {
            "with_genres": genre,
            "primary_release_year": year,
            "with_original_language": language,
        }
        if min_rating is not None:
            filters["vote_average.gte"] = min_rating
            filters["vote_count.gte"] = 100
        data = await _safe(tmdb.discover(page=page, **filters))
        results = catalog.cards_from_page(data, streamable)

    # Surface library-only titles (no TMDB entry) at the top of the first page.
    if q and page == 1:
        local = await db.scalars(
            select(Movie)
            .where(catalog.streamable_filter(), Movie.tmdb_id.is_(None), Movie.title.ilike(f"%{q}%"))
            .limit(10)
        )
        results = [catalog.card_from_movie(m, True) for m in local] + results

    return MoviePage(
        page=data.get("page", page),
        total_pages=min(data.get("total_pages", 0), 500),
        total_results=data.get("total_results", len(results)),
        results=results,
    )


async def local_search(
    db: AsyncSession, q: str | None, genre: int | None, year: int | None, language: str | None,
    min_rating: float | None, page: int, page_size: int = 40,
) -> MoviePage:
    """Search the local catalog (streamable library + imported catalog) when TMDB isn't configured."""
    stmt = select(Movie).where(or_(Movie.in_library.is_(False), catalog.streamable_filter()))
    if q:
        stmt = stmt.where(Movie.title.ilike(f"%{q.replace('%', '').replace('_', '')}%"))
    if year:
        stmt = stmt.where(func.extract("year", Movie.release_date) == year)
    if language:
        stmt = stmt.where(Movie.original_language == language)
    if min_rating is not None:
        stmt = stmt.where(Movie.vote_average >= min_rating)
    if genre:
        stmt = stmt.where(Movie.genres.any(Genre.id == genre))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    movies = list(await db.scalars(
        stmt.order_by(Movie.popularity.desc().nulls_last(), Movie.title).offset((page - 1) * page_size).limit(page_size)
    ))  # fmt: skip
    return MoviePage(page=page, total_pages=max(1, -(-total // page_size)), total_results=total,
                     results=await cards_for_movies(db, movies))  # fmt: skip


@router.get("/movies/{key}", response_model=MovieDetail)
async def movie_detail(db: DB, tmdb: TMDB, key: str = MOVIE_KEY) -> MovieDetail:
    movie = await catalog.get_movie_by_key(db, key)
    availability, _ = await catalog.availability_for(db, movie)

    if key.isdigit():
        try:
            data = await tmdb.movie(int(key))
        except TMDBNotFound:
            data = None
        except TMDBError as exc:
            if movie is None:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Metadata provider unavailable") from exc
            data = None
        if data is not None:
            streamable = await catalog.streamable_tmdb_ids(db)
            return catalog.detail_from_tmdb(data, availability, streamable, settings.TMDB_REGION)
        if movie is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Movie not found")
        return catalog.detail_from_movie(movie, availability)

    is_catalog_entry = movie is not None and (movie.external_id or "").startswith("wd:")
    if movie is None or not (is_catalog_entry or (movie.in_library and availability.streamable)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Movie not found")
    detail = catalog.detail_from_movie(movie, availability)
    if is_catalog_entry:
        # Metadata-only title (Wikidata catalog): similar = notable films sharing a genre.
        genre_ids = [g.id for g in movie.genres]
        stmt = select(Movie).where(Movie.original_language == movie.original_language, Movie.id != movie.id)
        if genre_ids:
            stmt = stmt.where(Movie.genres.any(Genre.id.in_(genre_ids)))
        similar = list(await db.scalars(stmt.order_by(Movie.popularity.desc().nulls_last()).limit(18)))
        detail.similar = await cards_for_movies(db, similar)
    else:
        others, _ = await free_to_watch(db, 1, 13)
        detail.similar = [catalog.card_from_movie(m, True) for m in others if m.id != movie.id][:12]
    return detail


@router.get("/movies/{key}/trailer", response_model=TrailerOut)
async def movie_trailer(db: DB, tmdb: TMDB, key: str = MOVIE_KEY) -> TrailerOut:
    """Lightweight endpoint for hover previews on poster cards."""
    if key.isdigit():
        try:
            data = await tmdb.videos(int(key))
            return TrailerOut(trailer=catalog.pick_trailer(data.get("results", [])))
        except TMDBError:
            return TrailerOut(trailer=None)
    movie = await catalog.get_movie_by_key(db, key)
    return TrailerOut(
        trailer=catalog.Video(key=movie.trailer_key, name="Trailer") if movie and movie.trailer_key else None
    )


async def cards_for_movies(db: AsyncSession, movies: list[Movie]) -> list[MovieCard]:
    """Cards for local rows with accurate `streamable` flags."""
    if not movies:
        return []
    ids = [m.id for m in movies]
    streamable_ids: set[uuid.UUID] = set(
        await db.scalars(select(Movie.id).where(Movie.id.in_(ids), catalog.streamable_filter()))
    )
    return [catalog.card_from_movie(m, m.id in streamable_ids) for m in movies]
