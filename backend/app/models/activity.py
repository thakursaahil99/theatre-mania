import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPk
from app.models.movie import Movie


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    movie: Mapped[Movie] = relationship(lazy="joined")


class WatchProgress(Base):
    """Latest resume point per profile+movie. Powers Continue Watching and History."""

    __tablename__ = "watch_progress"
    __table_args__ = (Index("ix_watch_progress_profile_updated", "profile_id", "updated_at"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_assets.id", ondelete="SET NULL"))
    position_sec: Mapped[float] = mapped_column(Float, default=0)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    movie: Mapped[Movie] = relationship(lazy="joined")


class WatchSession(UUIDPk, Base):
    """One row per playback start. Aggregated for admin analytics (views, watch time)."""

    __tablename__ = "watch_sessions"
    __table_args__ = (Index("ix_watch_sessions_movie_started", "movie_id", "started_at"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_assets.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seconds_watched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_position_sec: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (CheckConstraint("score BETWEEN 1 AND 5", name="score_range"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
