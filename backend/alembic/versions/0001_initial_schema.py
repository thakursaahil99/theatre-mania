"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _ts(name: str, nullable: bool = False, default: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable,
                     server_default=sa.func.now() if default else None)  # fmt: skip


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("google_sub", sa.String(255)),
        sa.Column("display_name", sa.String(80)),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE",
                  name="fk_refresh_tokens_user_id_users"), nullable=False),  # fmt: skip
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String(255)),
        _ts("created_at"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE",
                  name="fk_profiles_user_id_users"), nullable=False),  # fmt: skip
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("avatar", sa.String(32), nullable=False),
        sa.Column("is_kids", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("user_id", "name", name="uq_profiles_user_id_name"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])

    op.create_table("genres", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
                    sa.Column("name", sa.String(64), nullable=False))  # fmt: skip

    op.create_table(
        "movies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tmdb_id", sa.Integer()),
        sa.Column("imdb_id", sa.String(16)),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("original_title", sa.String(255)),
        sa.Column("overview", sa.Text()),
        sa.Column("tagline", sa.String(500)),
        sa.Column("release_date", sa.Date()),
        sa.Column("runtime", sa.Integer()),
        sa.Column("original_language", sa.String(8)),
        sa.Column("vote_average", sa.Float()),
        sa.Column("vote_count", sa.Integer()),
        sa.Column("popularity", sa.Float()),
        sa.Column("poster_path", sa.String(512)),
        sa.Column("backdrop_path", sa.String(512)),
        sa.Column("trailer_key", sa.String(32)),
        sa.Column("certification", sa.String(16)),
        sa.Column("credits", JSONB),
        sa.Column("in_library", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("metadata_synced_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_movies_tmdb_id", "movies", ["tmdb_id"], unique=True)
    op.create_index("ix_movies_slug", "movies", ["slug"], unique=True)
    op.create_index("ix_movies_title", "movies", ["title"])
    op.create_index("ix_movies_in_library", "movies", ["in_library"])
    op.create_index("ix_movies_status", "movies", ["status"])

    op.create_table(
        "movie_genres",
        sa.Column("movie_id", sa.Uuid(), sa.ForeignKey("movies.id", ondelete="CASCADE",
                  name="fk_movie_genres_movie_id_movies"), primary_key=True),  # fmt: skip
        sa.Column("genre_id", sa.Integer(), sa.ForeignKey("genres.id", ondelete="CASCADE",
                  name="fk_movie_genres_genre_id_genres"), primary_key=True),  # fmt: skip
    )

    op.create_table(
        "licenses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("movie_id", sa.Uuid(), sa.ForeignKey("movies.id", ondelete="CASCADE",
                  name="fk_licenses_movie_id_movies"), nullable=False),  # fmt: skip
        sa.Column("license_type", sa.String(32), nullable=False),
        sa.Column("licensor", sa.String(255)),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("territories", JSONB, nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        _ts("created_at"),
    )
    op.create_index("ix_licenses_movie_id", "licenses", ["movie_id"])
    op.create_index("ix_licenses_expires_at", "licenses", ["expires_at"])

    op.create_table(
        "video_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("movie_id", sa.Uuid(), sa.ForeignKey("movies.id", ondelete="CASCADE",
                  name="fk_video_assets_movie_id_movies"), nullable=False),  # fmt: skip
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_key", sa.String(512)),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("storage_prefix", sa.String(512)),
        sa.Column("master_key", sa.String(512)),
        sa.Column("thumbnail_key", sa.String(512)),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("renditions", JSONB),
        sa.Column("intro_start_sec", sa.Float()),
        sa.Column("intro_end_sec", sa.Float()),
        sa.Column("credits_start_sec", sa.Float()),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("celery_task_id", sa.String(64)),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_video_assets_movie_id", "video_assets", ["movie_id"])
    op.create_index("ix_video_assets_status", "video_assets", ["status"])

    op.create_table(
        "subtitles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("video_assets.id", ondelete="CASCADE",
                  name="fk_subtitles_asset_id_video_assets"), nullable=False),  # fmt: skip
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        _ts("created_at"),
    )
    op.create_index("ix_subtitles_asset_id", "subtitles", ["asset_id"])

    def profile_fk(table: str) -> sa.Column:
        return sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE",
                         name=f"fk_{table}_profile_id_profiles"), primary_key=True)  # fmt: skip

    def movie_fk(table: str, pk: bool = True) -> sa.Column:
        return sa.Column("movie_id", sa.Uuid(), sa.ForeignKey("movies.id", ondelete="CASCADE",
                         name=f"fk_{table}_movie_id_movies"), primary_key=pk, nullable=False)  # fmt: skip

    op.create_table("watchlist_items", profile_fk("watchlist_items"), movie_fk("watchlist_items"), _ts("added_at"))
    op.create_index("ix_watchlist_items_added_at", "watchlist_items", ["added_at"])

    op.create_table(
        "watch_progress",
        profile_fk("watch_progress"),
        movie_fk("watch_progress"),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("video_assets.id", ondelete="SET NULL",
                  name="fk_watch_progress_asset_id_video_assets")),  # fmt: skip
        sa.Column("position_sec", sa.Float(), nullable=False),
        sa.Column("duration_sec", sa.Float()),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        _ts("updated_at"),
    )
    op.create_index("ix_watch_progress_profile_updated", "watch_progress", ["profile_id", "updated_at"])

    op.create_table(
        "watch_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE",
                  name="fk_watch_sessions_profile_id_profiles"), nullable=False),  # fmt: skip
        movie_fk("watch_sessions", pk=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("video_assets.id", ondelete="SET NULL",
                  name="fk_watch_sessions_asset_id_video_assets")),  # fmt: skip
        _ts("started_at"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("seconds_watched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_position_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_watch_sessions_profile_id", "watch_sessions", ["profile_id"])
    op.create_index("ix_watch_sessions_started_at", "watch_sessions", ["started_at"])
    op.create_index("ix_watch_sessions_movie_started", "watch_sessions", ["movie_id", "started_at"])

    op.create_table(
        "ratings",
        profile_fk("ratings"),
        movie_fk("ratings"),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_ratings_score_range"),
    )


def downgrade() -> None:
    for table in [
        "ratings", "watch_sessions", "watch_progress", "watchlist_items", "subtitles",
        "video_assets", "licenses", "movie_genres", "movies", "genres", "profiles",
        "refresh_tokens", "users",
    ]:  # fmt: skip
        op.drop_table(table)
