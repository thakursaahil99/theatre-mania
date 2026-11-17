import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.movie import AssetStatus, LicenseType, MovieStatus


class LicenseIn(BaseModel):
    license_type: LicenseType
    licensor: str | None = Field(default=None, max_length=255)
    source_url: HttpUrl | None = None
    territories: list[str] = Field(default_factory=lambda: ["WW"])
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def check_window(self) -> "LicenseIn":
        if self.starts_at and self.expires_at and self.expires_at <= self.starts_at:
            raise ValueError("expires_at must be after starts_at")
        if self.license_type == LicenseType.licensed and not self.licensor:
            raise ValueError("licensor is required for licensed content")
        self.territories = [t.upper() for t in self.territories]
        return self


class LicenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    license_type: LicenseType
    licensor: str | None
    source_url: str | None
    territories: list[str]
    starts_at: datetime | None
    expires_at: datetime | None
    notes: str | None


class SubtitleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    language: str
    label: str
    is_default: bool


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: AssetStatus
    progress: int
    source_url: str | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    renditions: list[dict] | None
    intro_start_sec: float | None
    intro_end_sec: float | None
    credits_start_sec: float | None
    error: str | None
    subtitles: list[SubtitleOut]
    created_at: datetime
    updated_at: datetime


class AssetPatch(BaseModel):
    intro_start_sec: float | None = Field(default=None, ge=0)
    intro_end_sec: float | None = Field(default=None, ge=0)
    credits_start_sec: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_intro(self) -> "AssetPatch":
        if self.intro_start_sec is not None and self.intro_end_sec is not None:
            if self.intro_end_sec <= self.intro_start_sec:
                raise ValueError("intro_end_sec must be after intro_start_sec")
        return self


class AdminMovieCreate(BaseModel):
    tmdb_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=255)
    overview: str | None = None
    release_date: date | None = None
    license: LicenseIn

    @model_validator(mode="after")
    def need_identity(self) -> "AdminMovieCreate":
        if not self.tmdb_id and not self.title:
            raise ValueError("Provide a tmdb_id or a title")
        return self


class AdminMoviePatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    overview: str | None = None
    tagline: str | None = Field(default=None, max_length=500)
    poster_path: str | None = Field(default=None, max_length=512)
    backdrop_path: str | None = Field(default=None, max_length=512)
    trailer_key: str | None = Field(default=None, max_length=32)
    release_date: date | None = None


class AdminMovieOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tmdb_id: int | None
    slug: str
    title: str
    overview: str | None
    tagline: str | None
    release_date: date | None
    runtime: int | None
    poster_path: str | None
    backdrop_path: str | None
    trailer_key: str | None
    status: MovieStatus
    published_at: datetime | None
    metadata_synced_at: datetime | None
    license: LicenseOut | None = None
    license_active: bool = False
    assets: list[AssetOut] = []
    created_at: datetime


class AdminMovieList(BaseModel):
    items: list[AdminMovieOut]
    total: int
    page: int
    page_size: int


class UploadUrlIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(pattern=r"^video/[\w.+-]+$")
    size_bytes: int = Field(gt=0, le=5 * 1024**3)  # single-PUT limit on S3/R2


class UploadUrlOut(BaseModel):
    asset_id: uuid.UUID
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str]


class ImportIn(BaseModel):
    source_url: HttpUrl


class DailyStat(BaseModel):
    date: date
    views: int
    watch_minutes: float


class TopMovie(BaseModel):
    movie_id: uuid.UUID
    title: str
    poster_path: str | None
    views: int
    watch_minutes: float


class AnalyticsOut(BaseModel):
    days: int
    views: int
    watch_hours: float
    unique_viewers: int
    library_size: int
    published: int
    expiring_soon: int
    processing_jobs: int
    daily: list[DailyStat]
    top_movies: list[TopMovie]
