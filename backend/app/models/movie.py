import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPk


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # VARCHAR + CHECK instead of native PG enums: painless to extend in migrations.
    return Enum(cls, name=name, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class MovieStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class LicenseType(str, enum.Enum):
    public_domain = "public_domain"
    creative_commons = "creative_commons"
    owned = "owned"
    licensed = "licensed"


class AssetStatus(str, enum.Enum):
    pending_upload = "pending_upload"
    queued = "queued"
    downloading = "downloading"
    processing = "processing"
    ready = "ready"
    failed = "failed"


movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # TMDB genre id
    name: Mapped[str] = mapped_column(String(64))


class Movie(UUIDPk, Timestamps, Base):
    """A title known to Theatre Mania.

    `in_library=True` rows are titles we hold streaming rights for (they have a License and
    VideoAssets). `in_library=False` rows are lightweight TMDB catalog stubs created on demand
    so watchlists/ratings can reference any movie with a real foreign key.
    """

    __tablename__ = "movies"

    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)
    # Stable id in an external public-domain source, e.g. "ia:<identifier>" (idempotent imports).
    external_id: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(16))
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    original_title: Mapped[str | None] = mapped_column(String(255))
    overview: Mapped[str | None] = mapped_column(Text)
    tagline: Mapped[str | None] = mapped_column(String(500))
    release_date: Mapped[date | None] = mapped_column(Date)
    runtime: Mapped[int | None] = mapped_column(Integer)
    original_language: Mapped[str | None] = mapped_column(String(8))
    vote_average: Mapped[float | None] = mapped_column(Float)
    vote_count: Mapped[int | None] = mapped_column(Integer)
    popularity: Mapped[float | None] = mapped_column(Float)
    poster_path: Mapped[str | None] = mapped_column(String(512))
    backdrop_path: Mapped[str | None] = mapped_column(String(512))
    trailer_key: Mapped[str | None] = mapped_column(String(32))
    certification: Mapped[str | None] = mapped_column(String(16))
    # Cached cast/crew snapshot for library titles (rendered without a TMDB round-trip).
    credits: Mapped[dict[str, Any] | None] = mapped_column()

    in_library: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    status: Mapped[MovieStatus] = mapped_column(
        _enum(MovieStatus, "movie_status"), default=MovieStatus.draft, server_default="draft", index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    genres: Mapped[list[Genre]] = relationship(secondary=movie_genres, lazy="selectin")
    licenses: Mapped[list["License"]] = relationship(
        back_populates="movie", cascade="all, delete-orphan", lazy="selectin", order_by="License.created_at"
    )
    assets: Mapped[list["VideoAsset"]] = relationship(
        back_populates="movie", cascade="all, delete-orphan", order_by="VideoAsset.created_at"
    )


class License(UUIDPk, Base):
    __tablename__ = "licenses"

    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    license_type: Mapped[LicenseType] = mapped_column(_enum(LicenseType, "license_type"))
    licensor: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    # ISO-3166 alpha-2 codes, or ["WW"] for worldwide.
    territories: Mapped[list[Any]] = mapped_column(default=lambda: ["WW"])
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    movie: Mapped[Movie] = relationship(back_populates="licenses")


class VideoAsset(UUIDPk, Timestamps, Base):
    __tablename__ = "video_assets"

    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    status: Mapped[AssetStatus] = mapped_column(
        _enum(AssetStatus, "asset_status"), default=AssetStatus.pending_upload, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    source_key: Mapped[str | None] = mapped_column(String(512))  # uploaded original in the bucket
    source_url: Mapped[str | None] = mapped_column(String(1024))  # remote import (e.g. archive.org)
    storage_prefix: Mapped[str | None] = mapped_column(String(512))  # e.g. hls/<asset-id>
    master_key: Mapped[str | None] = mapped_column(String(512))
    thumbnail_key: Mapped[str | None] = mapped_column(String(512))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    # [{"name": "720p", "height": 720, "bandwidth": 3000000, "playlist": "720p/index.m3u8"}]
    renditions: Mapped[list[Any] | None] = mapped_column()
    intro_start_sec: Mapped[float | None] = mapped_column(Float)
    intro_end_sec: Mapped[float | None] = mapped_column(Float)
    credits_start_sec: Mapped[float | None] = mapped_column(Float)
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    # Direct progressive source on a public-domain host (e.g. archive.org MP4). When set, the
    # player streams it as-is instead of our HLS renditions: no download, no transcode.
    playback_url: Mapped[str | None] = mapped_column(String(1024))

    movie: Mapped[Movie] = relationship(back_populates="assets")
    subtitles: Mapped[list["Subtitle"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )


class Subtitle(UUIDPk, Base):
    __tablename__ = "subtitles"

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("video_assets.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    label: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[VideoAsset] = relationship(back_populates="subtitles")
