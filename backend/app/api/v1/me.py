"""Per-profile library: watchlist, continue watching, history, ratings."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from app.api.deps import DB, TMDB, CurrentProfile
from app.api.v1.movies import MOVIE_KEY, cards_for_movies
from app.models import Rating, WatchlistItem, WatchProgress
from app.schemas.movie import MovieCard, MovieState, ProgressItem, RatingIn
from app.services import catalog

router = APIRouter(prefix="/me", tags=["me"])


async def _resolve(db: DB, tmdb: TMDB, key: str):
    try:
        return await catalog.ensure_movie(db, tmdb, key)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Movie not found") from None


@router.get("/watchlist", response_model=list[MovieCard])
async def get_watchlist(profile: CurrentProfile, db: DB) -> list[MovieCard]:
    items = await db.scalars(
        select(WatchlistItem).where(WatchlistItem.profile_id == profile.id).order_by(WatchlistItem.added_at.desc())
    )
    return await cards_for_movies(db, [i.movie for i in items.unique()])


@router.put("/watchlist/{key}", status_code=204)
async def add_to_watchlist(profile: CurrentProfile, db: DB, tmdb: TMDB, key: str = MOVIE_KEY) -> None:
    movie = await _resolve(db, tmdb, key)
    if await db.get(WatchlistItem, (profile.id, movie.id)) is None:
        db.add(WatchlistItem(profile_id=profile.id, movie_id=movie.id))
    await db.commit()


@router.delete("/watchlist/{key}", status_code=204)
async def remove_from_watchlist(profile: CurrentProfile, db: DB, key: str = MOVIE_KEY) -> None:
    movie = await catalog.get_movie_by_key(db, key)
    if movie:
        await db.execute(
            delete(WatchlistItem).where(WatchlistItem.profile_id == profile.id, WatchlistItem.movie_id == movie.id)
        )
        await db.commit()


async def _progress_items(db: DB, rows: list[WatchProgress]) -> list[ProgressItem]:
    cards = await cards_for_movies(db, [r.movie for r in rows])
    return [
        ProgressItem(
            movie=card,
            position_sec=r.position_sec,
            duration_sec=r.duration_sec,
            completed=r.completed,
            updated_at=r.updated_at,
        )
        for r, card in zip(rows, cards, strict=True)
    ]


@router.get("/continue-watching", response_model=list[ProgressItem])
async def continue_watching(profile: CurrentProfile, db: DB) -> list[ProgressItem]:
    rows = list(
        (
            await db.scalars(
                select(WatchProgress)
                .where(
                    WatchProgress.profile_id == profile.id,
                    WatchProgress.completed.is_(False),
                    WatchProgress.position_sec >= 30,
                )
                .order_by(WatchProgress.updated_at.desc())
                .limit(20)
            )
        ).unique()
    )
    items = await _progress_items(db, rows)
    return [i for i in items if i.movie.streamable]


@router.get("/history", response_model=list[ProgressItem])
async def history(profile: CurrentProfile, db: DB, limit: int = Query(50, ge=1, le=200)) -> list[ProgressItem]:
    rows = list(
        (
            await db.scalars(
                select(WatchProgress)
                .where(WatchProgress.profile_id == profile.id)
                .order_by(WatchProgress.updated_at.desc())
                .limit(limit)
            )
        ).unique()
    )
    return await _progress_items(db, rows)


@router.delete("/history/{key}", status_code=204)
async def remove_history(profile: CurrentProfile, db: DB, key: str = MOVIE_KEY) -> None:
    movie = await catalog.get_movie_by_key(db, key)
    if movie:
        await db.execute(
            delete(WatchProgress).where(WatchProgress.profile_id == profile.id, WatchProgress.movie_id == movie.id)
        )
        await db.commit()


@router.put("/ratings/{key}", response_model=MovieState)
async def rate(body: RatingIn, profile: CurrentProfile, db: DB, tmdb: TMDB, key: str = MOVIE_KEY) -> MovieState:
    if not 1 <= body.score <= 5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Score must be between 1 and 5")
    movie = await _resolve(db, tmdb, key)
    rating = await db.get(Rating, (profile.id, movie.id))
    if rating is None:
        db.add(Rating(profile_id=profile.id, movie_id=movie.id, score=body.score))
    else:
        rating.score = body.score
    await db.commit()
    return await movie_state(profile, db, key)


@router.delete("/ratings/{key}", status_code=204)
async def unrate(profile: CurrentProfile, db: DB, key: str = MOVIE_KEY) -> None:
    movie = await catalog.get_movie_by_key(db, key)
    if movie:
        await db.execute(delete(Rating).where(Rating.profile_id == profile.id, Rating.movie_id == movie.id))
        await db.commit()


@router.get("/state/{key}", response_model=MovieState)
async def movie_state(profile: CurrentProfile, db: DB, key: str = MOVIE_KEY) -> MovieState:
    movie = await catalog.get_movie_by_key(db, key)
    if movie is None:
        return MovieState(in_watchlist=False, rating=None, position_sec=None, duration_sec=None, completed=False)
    in_list = await db.get(WatchlistItem, (profile.id, movie.id)) is not None
    rating = await db.get(Rating, (profile.id, movie.id))
    progress = await db.get(WatchProgress, (profile.id, movie.id))
    return MovieState(
        in_watchlist=in_list,
        rating=rating.score if rating else None,
        position_sec=progress.position_sec if progress else None,
        duration_sec=progress.duration_sec if progress else None,
        completed=progress.completed if progress else False,
    )
