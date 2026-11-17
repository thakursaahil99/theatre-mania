"""Bollywood (Hindi-language cinema) rows, built from TMDB Discover.

Every row is metadata + trailers + Indian "Where to Watch" providers. Titles only become
streamable on Theatre Mania if they are in the licensed library, like any other film.
"""

from datetime import date, timedelta
from typing import Any

# (slug, row title). Order = order on the Bollywood page.
ROWS: list[tuple[str, str]] = [
    ("trending", "Trending in Bollywood"),
    ("new", "New Bollywood Releases"),
    ("top", "Bollywood's Highest Rated"),
    ("romance", "Bollywood Romance"),
    ("action", "Bollywood Action"),
    ("comedy", "Bollywood Comedy"),
    ("thriller", "Thrillers & Crime"),
    ("family", "Family Favourites"),
    ("classics", "Golden-Era Classics"),
]
TITLES = dict(ROWS)
# Rows that also appear on the main home page.
HOME_ROWS = ("trending", "new")

_BASE: dict[str, Any] = {"with_original_language": "hi", "region": "IN"}
_GENRES = {"romance": "10749", "action": "28", "comedy": "35", "thriller": "53|80", "family": "10751"}


def filters(slug: str, today: date | None = None) -> dict[str, Any] | None:
    """TMDB Discover parameters for a row, or None for an unknown slug."""
    today = today or date.today()
    if slug == "trending":
        return {**_BASE, "sort_by": "popularity.desc", "vote_count.gte": 20}
    if slug == "new":
        return {
            **_BASE,
            "sort_by": "primary_release_date.desc",
            "primary_release_date.gte": (today - timedelta(days=180)).isoformat(),
            "primary_release_date.lte": today.isoformat(),
            "vote_count.gte": 3,
        }
    if slug == "top":
        return {**_BASE, "sort_by": "vote_average.desc", "vote_count.gte": 300}
    if slug == "classics":
        return {**_BASE, "sort_by": "vote_average.desc", "vote_count.gte": 60, "primary_release_date.lte": "1989-12-31"}
    if slug in _GENRES:
        return {**_BASE, "sort_by": "popularity.desc", "with_genres": _GENRES[slug], "vote_count.gte": 40}
    return None


# ------------------------------------------------------------------ local catalog (no TMDB key)
# Same rows, served from the Wikidata-imported catalog (scripts/import_wikidata.py) when TMDB
# isn't configured. Includes streamable library titles in Hindi too.

_ROW_GENRES = {"romance": (10749,), "action": (28,), "comedy": (35,), "thriller": (53, 80), "family": (10751,)}


def local_query(slug: str, today: date | None = None):
    """SQLAlchemy select for a row from the local catalog, or None for an unknown slug."""
    from sqlalchemy import or_, select

    from app.models import Genre, Movie
    from app.services.catalog import streamable_filter

    if slug not in TITLES:
        return None
    today = today or date.today()
    stmt = select(Movie).where(
        Movie.original_language == "hi",
        or_(Movie.in_library.is_(False), streamable_filter()),
    )
    by_popularity = (Movie.popularity.desc().nulls_last(), Movie.title)
    if slug == "trending":
        stmt = stmt.where(Movie.release_date >= today - timedelta(days=3 * 365), Movie.release_date <= today)
        return stmt.order_by(*by_popularity)
    if slug == "new":
        stmt = stmt.where(Movie.release_date <= today)
        return stmt.order_by(Movie.release_date.desc().nulls_last(), *by_popularity)
    if slug == "classics":
        return stmt.where(Movie.release_date <= date(1989, 12, 31)).order_by(*by_popularity)
    if slug in _ROW_GENRES:
        return stmt.where(Movie.genres.any(Genre.id.in_(_ROW_GENRES[slug]))).order_by(*by_popularity)
    return stmt.order_by(*by_popularity)  # "top": most notable of all time
