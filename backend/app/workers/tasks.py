import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core import storage
from app.core.config import settings
from app.core.time import utcnow
from app.models import AssetStatus, Genre, Movie, MovieStatus, VideoAsset
from app.services.catalog import genre_pairs, license_is_active, movie_fields_from_tmdb
from app.services.tmdb import TMDBClient
from app.workers import transcode as tx
from app.workers.celery_app import celery_app
from app.workers.db import invalidate_api_caches, session_scope

log = logging.getLogger(__name__)


def _update_asset(asset_id: str, **fields) -> None:
    with session_scope() as db:
        asset = db.get(VideoAsset, uuid.UUID(asset_id))
        if asset is not None:
            for k, v in fields.items():
                setattr(asset, k, v)


@celery_app.task(bind=True, name="app.workers.tasks.transcode_asset", max_retries=1, time_limit=10 * 3600,
                 soft_time_limit=9 * 3600)  # fmt: skip
def transcode_asset(self, asset_id: str) -> dict:
    with session_scope() as db:
        asset = db.get(VideoAsset, uuid.UUID(asset_id))
        if asset is None:
            return {"status": "missing"}
        source_key, source_url, movie_id = asset.source_key, asset.source_url, asset.movie_id
        asset.status, asset.progress, asset.error = AssetStatus.downloading, 0, None
        asset.celery_task_id = self.request.id

    workdir = Path(settings.TRANSCODE_WORKDIR) / asset_id
    shutil.rmtree(workdir, ignore_errors=True)
    out_dir = workdir / "hls"
    out_dir.mkdir(parents=True)
    src = workdir / "source"

    try:
        # 1. Fetch the mezzanine file.
        if source_url:
            tx.download(source_url, src, lambda p: _update_asset(asset_id, progress=p))
        elif source_key:
            storage.download_file(source_key, src)
        else:
            raise tx.TranscodeError("Asset has neither an uploaded file nor a source URL")

        # 2. Probe + transcode.
        info = tx.probe(src)
        rungs = tx.select_ladder(info.height)
        for r in rungs:
            (out_dir / r.name).mkdir()
        _update_asset(asset_id, status=AssetStatus.processing, progress=0, duration_seconds=info.duration,
                      width=info.width, height=info.height)  # fmt: skip
        tx.run_ffmpeg(
            tx.build_ffmpeg_command(src, out_dir, rungs, info.has_audio),
            info.duration,
            lambda p: _update_asset(asset_id, progress=p),
            workdir / "ffmpeg.log",
        )
        renditions = tx.write_master_playlist(out_dir, rungs, info)
        has_thumb = tx.extract_thumbnail(src, out_dir / "thumb.jpg", min(info.duration * 0.1, 300))

        # 3. Publish to object storage.
        prefix = f"hls/{asset_id}"
        storage.upload_directory(out_dir, prefix)

        with session_scope() as db:
            asset = db.get(VideoAsset, uuid.UUID(asset_id))
            asset.status = AssetStatus.ready
            asset.progress = 100
            asset.storage_prefix = prefix
            asset.master_key = f"{prefix}/master.m3u8"
            asset.thumbnail_key = f"{prefix}/thumb.jpg" if has_thumb else None
            asset.renditions = renditions
            movie = db.get(Movie, movie_id)
            if movie and not movie.runtime:
                movie.runtime = round(info.duration / 60)
        invalidate_api_caches()
        return {"status": "ready", "renditions": [r["name"] for r in renditions]}
    except Exception as exc:
        log.exception("transcode failed for %s", asset_id)
        _update_asset(asset_id, status=AssetStatus.failed, error=str(exc)[:4000])
        raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@celery_app.task(name="app.workers.tasks.refresh_metadata", max_retries=3, default_retry_delay=60)
def refresh_metadata(movie_id: str) -> dict:
    with session_scope() as db:
        movie = db.get(Movie, uuid.UUID(movie_id))
        if movie is None or movie.tmdb_id is None:
            return {"status": "skipped"}
        tmdb_id = movie.tmdb_id

    async def fetch():
        async with TMDBClient.standalone() as tmdb:
            return await tmdb.movie(tmdb_id)

    data = asyncio.run(fetch())
    with session_scope() as db:
        movie = db.get(Movie, uuid.UUID(movie_id))
        for field, value in movie_fields_from_tmdb(data).items():
            setattr(movie, field, value)
        genres = []
        for gid, name in genre_pairs(data):
            genre = db.get(Genre, gid) or Genre(id=gid, name=name)
            genres.append(genre)
        movie.genres = genres
        movie.metadata_synced_at = utcnow()
    invalidate_api_caches()
    return {"status": "ok"}


@celery_app.task(name="app.workers.tasks.enforce_license_windows")
def enforce_license_windows() -> dict:
    """Unpublish anything whose license window has closed. Playback also checks at request time."""
    unpublished = []
    with session_scope() as db:
        movies = db.scalars(select(Movie).where(Movie.in_library.is_(True), Movie.status == MovieStatus.published))
        now = utcnow()
        for movie in movies:
            if not any(license_is_active(lic, now) for lic in movie.licenses):
                movie.status = MovieStatus.draft
                unpublished.append(str(movie.id))
    if unpublished:
        log.info("unpublished %d titles with expired licenses", len(unpublished))
        invalidate_api_caches()
    return {"unpublished": unpublished}
