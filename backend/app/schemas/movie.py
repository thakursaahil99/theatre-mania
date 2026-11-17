"""Public catalog shapes. The frontend only ever sees these, never raw TMDB payloads."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GenreOut(BaseModel):
    id: int
    name: str


class MovieCard(BaseModel):
    # Route key used by the frontend: str(tmdb_id) for TMDB titles, or a slug for
    # library-only titles that have no TMDB entry.
    id: str
    tmdb_id: int | None = None
    title: str
    overview: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    release_date: str | None = None
    vote_average: float | None = None
    genre_ids: list[int] = []
    original_language: str | None = None
    streamable: bool = False


class MovieRow(BaseModel):
    id: str
    title: str
    items: list[MovieCard]
    href: str | None = None


class CastMember(BaseModel):
    id: int
    name: str
    character: str | None = None
    profile_path: str | None = None


class CrewMember(BaseModel):
    id: int
    name: str
    job: str


class Video(BaseModel):
    key: str
    name: str
    site: str = "YouTube"
    type: str = "Trailer"


class Provider(BaseModel):
    provider_id: int
    provider_name: str
    logo_path: str | None = None


class WatchProviders(BaseModel):
    region: str
    link: str | None = None
    flatrate: list[Provider] = []
    rent: list[Provider] = []
    buy: list[Provider] = []
    free: list[Provider] = []


class Availability(BaseModel):
    streamable: bool
    license_type: str | None = None
    expires_at: datetime | None = None
    duration_seconds: float | None = None
    has_subtitles: bool = False


class ExternalLink(BaseModel):
    # where_to_watch | trailer_search | imdb | wikipedia | wikidata
    kind: str
    label: str
    url: str


class MovieDetail(MovieCard):
    tagline: str | None = None
    runtime: int | None = None
    genres: list[GenreOut] = []
    certification: str | None = None
    imdb_id: str | None = None
    cast: list[CastMember] = []
    directors: list[CrewMember] = []
    trailer: Video | None = None
    videos: list[Video] = []
    similar: list[MovieCard] = []
    watch_providers: WatchProviders | None = None
    links: list[ExternalLink] = []
    availability: Availability


class HomeOut(BaseModel):
    hero: list[MovieDetail]
    rows: list[MovieRow]


class MoviePage(BaseModel):
    page: int
    total_pages: int
    total_results: int
    results: list[MovieCard]


class TrailerOut(BaseModel):
    trailer: Video | None


class MovieState(BaseModel):
    in_watchlist: bool
    rating: int | None
    position_sec: float | None
    duration_sec: float | None
    completed: bool


class ProgressItem(BaseModel):
    movie: MovieCard
    position_sec: float
    duration_sec: float | None
    completed: bool
    updated_at: datetime


class RatingIn(BaseModel):
    score: int


class PlaybackSubtitle(BaseModel):
    id: uuid.UUID
    language: str
    label: str
    url: str
    is_default: bool


class PlaybackOut(BaseModel):
    session_id: uuid.UUID
    asset_id: uuid.UUID
    movie: MovieCard
    master_url: str
    # "hls": tokenised playlists + signed segments. "mp4": direct public-domain source.
    stream_type: Literal["hls", "mp4"] = "hls"
    duration_seconds: float | None
    resume_position_sec: float
    intro_start_sec: float | None
    intro_end_sec: float | None
    credits_start_sec: float | None
    subtitles: list[PlaybackSubtitle]
    token_expires_in: int


class HeartbeatIn(BaseModel):
    position_sec: float
    duration_sec: float | None = None
    # Seconds actually played since the previous heartbeat (client measured).
    watched_delta_sec: float = 0
