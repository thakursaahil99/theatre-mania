import re
import uuid
from datetime import date, timedelta
from pathlib import PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, TMDB, AdminUser
from app.core import storage
from app.core.time import utcnow
from app.models import AssetStatus, License, Movie, MovieStatus, Subtitle, VideoAsset, WatchSession
from app.schemas.admin import (
    AdminMovieCreate,
    AdminMovieList,
    AdminMovieOut,
    AdminMoviePatch,
    AnalyticsOut,
    AssetOut,
    AssetPatch,
    DailyStat,
    ImportIn,
    LicenseIn,
    LicenseOut,
    TopMovie,
    UploadUrlIn,
    UploadUrlOut,
)
from app.services import catalog
from app.services.tmdb import TMDBError, TMDBNotFound
from app.workers.transcode import host_allowed

router = APIRouter(prefix="/admin", tags=["admin"])

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _enqueue_transcode(asset: VideoAsset) -> None:
    from app.workers.tasks import transcode_asset  # local import keeps API startup light

    result = transcode_asset.delay(str(asset.id))
    asset.celery_task_id = result.id
    asset.status = AssetStatus.queued
    asset.progress = 0
    asset.error = None


async def _load(db: DB, movie_id: uuid.UUID) -> Movie:
    movie = await db.scalar(
        select(Movie)
        .where(Movie.id == movie_id, Movie.in_library.is_(True))
        .options(selectinload(Movie.assets))
        .execution_options(populate_existing=True)
    )
    if movie is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Title not found")
    return movie


def _out(movie: Movie) -> AdminMovieOut:
    lic = movie.licenses[-1] if movie.licenses else None
    out = AdminMovieOut.model_validate(movie, from_attributes=True)
    out.license = LicenseOut.model_validate(lic) if lic else None
    out.license_active = bool(lic and catalog.license_is_active(lic))
    out.assets = [AssetOut.model_validate(a) for a in movie.assets]
    return out


async def _asset(db: DB, asset_id: uuid.UUID) -> VideoAsset:
    asset = await db.get(VideoAsset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


# ---------------------------------------------------------------- titles


@router.get("/tmdb/{tmdb_id}")
async def tmdb_lookup(tmdb_id: int, _: AdminUser, tmdb: TMDB) -> dict:
    """Preview TMDB metadata before adding a title."""
    try:
        data = await tmdb.movie(tmdb_id)
    except TMDBNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No TMDB title with that id") from None
    except TMDBError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    fields = catalog.movie_fields_from_tmdb(data)
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in fields.items() if k != "credits"}


@router.get("/movies", response_model=AdminMovieList)
async def list_titles(
    _: AdminUser,
    db: DB,
    q: str | None = Query(None, max_length=100),
    status_filter: MovieStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> AdminMovieList:
    stmt = select(Movie).where(Movie.in_library.is_(True))
    if q:
        stmt = stmt.where(Movie.title.ilike(f"%{q}%"))
    if status_filter:
        stmt = stmt.where(Movie.status == status_filter)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    movies = await db.scalars(
        stmt.options(selectinload(Movie.assets))
        .order_by(Movie.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return AdminMovieList(items=[_out(m) for m in movies], total=total, page=page, page_size=page_size)


@router.post("/movies", response_model=AdminMovieOut, status_code=201)
async def create_title(body: AdminMovieCreate, _: AdminUser, db: DB, tmdb: TMDB) -> AdminMovieOut:
    movie: Movie | None = None
    if body.tmdb_id:
        movie = await db.scalar(select(Movie).where(Movie.tmdb_id == body.tmdb_id))
        if movie and movie.in_library:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This TMDB title is already in the library")
        try:
            data = await tmdb.movie(body.tmdb_id)
        except TMDBNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No TMDB title with that id") from None
        except TMDBError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        if movie is None:  # promote an existing catalog stub, or create fresh
            movie = Movie(slug="pending", title=data.get("title") or "Untitled")
            db.add(movie)
        await catalog.apply_tmdb_metadata(db, movie, data)
        year = movie.release_date.year if movie.release_date else None
    else:
        year = body.release_date.year if body.release_date else None
        movie = Movie(title=body.title, overview=body.overview, release_date=body.release_date, slug="pending")
        db.add(movie)

    if body.title:
        movie.title = body.title
    movie.in_library = True
    movie.status = MovieStatus.draft
    movie.slug = await catalog.unique_slug(
        db, catalog.slugify(f"{movie.title} {year or ''}"), exclude_id=movie.id if movie.id else None
    )
    movie.licenses.append(License(**_license_values(body.license)))
    await db.commit()
    return _out(await _load(db, movie.id))


def _license_values(body: LicenseIn) -> dict:
    values = body.model_dump()
    values["source_url"] = str(body.source_url) if body.source_url else None
    return values


@router.get("/movies/{movie_id}", response_model=AdminMovieOut)
async def get_title(movie_id: uuid.UUID, _: AdminUser, db: DB) -> AdminMovieOut:
    return _out(await _load(db, movie_id))


@router.patch("/movies/{movie_id}", response_model=AdminMovieOut)
async def update_title(movie_id: uuid.UUID, body: AdminMoviePatch, _: AdminUser, db: DB) -> AdminMovieOut:
    movie = await _load(db, movie_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(movie, field, value)
    await db.commit()
    await catalog.invalidate_library_cache()
    return _out(await _load(db, movie_id))


@router.post("/movies/{movie_id}/refresh-metadata", response_model=AdminMovieOut)
async def refresh_title_metadata(movie_id: uuid.UUID, _: AdminUser, db: DB, tmdb: TMDB) -> AdminMovieOut:
    movie = await _load(db, movie_id)
    if not movie.tmdb_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Title has no TMDB id")
    # Bypass the 24h cache: admins expect fresh data when they click refresh.
    await tmdb.invalidate_movie(movie.tmdb_id)
    try:
        await catalog.apply_tmdb_metadata(db, movie, await tmdb.movie(movie.tmdb_id))
    except TMDBError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    await db.commit()
    await catalog.invalidate_library_cache()
    return _out(await _load(db, movie_id))


@router.put("/movies/{movie_id}/license", response_model=AdminMovieOut)
async def set_license(movie_id: uuid.UUID, body: LicenseIn, _: AdminUser, db: DB) -> AdminMovieOut:
    movie = await _load(db, movie_id)
    movie.licenses.append(License(**_license_values(body)))
    await db.commit()
    await catalog.invalidate_library_cache()
    return _out(await _load(db, movie_id))


@router.post("/movies/{movie_id}/publish", response_model=AdminMovieOut)
async def publish(movie_id: uuid.UUID, _: AdminUser, db: DB) -> AdminMovieOut:
    movie = await _load(db, movie_id)
    if catalog.active_license(movie) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Cannot publish without an active license")
    if catalog.primary_ready_asset(movie.assets) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Cannot publish until a video asset is ready")
    movie.status = MovieStatus.published
    movie.published_at = movie.published_at or utcnow()
    await db.commit()
    await catalog.invalidate_library_cache()
    return _out(await _load(db, movie_id))


@router.post("/movies/{movie_id}/unpublish", response_model=AdminMovieOut)
async def unpublish(movie_id: uuid.UUID, _: AdminUser, db: DB) -> AdminMovieOut:
    movie = await _load(db, movie_id)
    movie.status = MovieStatus.draft
    await db.commit()
    await catalog.invalidate_library_cache()
    return _out(await _load(db, movie_id))


@router.delete("/movies/{movie_id}", status_code=204)
async def delete_title(movie_id: uuid.UUID, _: AdminUser, db: DB) -> None:
    movie = await _load(db, movie_id)
    prefixes = [a.storage_prefix for a in movie.assets if a.storage_prefix]
    sources = [a.source_key for a in movie.assets if a.source_key]
    await db.delete(movie)
    await db.commit()
    await catalog.invalidate_library_cache()
    for prefix in prefixes:
        await run_in_threadpool(storage.delete_prefix, prefix)
    for key in sources:
        await run_in_threadpool(storage.delete_object, key)


# ---------------------------------------------------------------- assets


@router.post("/movies/{movie_id}/assets/upload-url", response_model=UploadUrlOut, status_code=201)
async def create_upload(movie_id: uuid.UUID, body: UploadUrlIn, _: AdminUser, db: DB) -> UploadUrlOut:
    movie = await _load(db, movie_id)
    asset_id = uuid.uuid4()
    filename = SAFE_NAME.sub("_", PurePosixPath(body.filename).name)[:120]
    key = f"uploads/{movie.id}/{asset_id}/{filename}"
    for a in movie.assets:
        a.is_primary = False
    db.add(VideoAsset(id=asset_id, movie_id=movie.id, status=AssetStatus.pending_upload, source_key=key))
    await db.commit()
    return UploadUrlOut(
        asset_id=asset_id,
        upload_url=storage.presign_put(key, body.content_type, expires=6 * 3600),
        headers={"Content-Type": body.content_type},
    )


@router.post("/assets/{asset_id}/complete", response_model=AssetOut)
async def complete_upload(asset_id: uuid.UUID, _: AdminUser, db: DB) -> VideoAsset:
    asset = await _asset(db, asset_id)
    if asset.status != AssetStatus.pending_upload or not asset.source_key:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Asset is not awaiting upload")
    if not await run_in_threadpool(storage.exists, asset.source_key):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Upload not found in storage yet")
    _enqueue_transcode(asset)
    await db.commit()
    return asset


@router.post("/movies/{movie_id}/assets/import", response_model=AssetOut, status_code=201)
async def import_asset(movie_id: uuid.UUID, body: ImportIn, _: AdminUser, db: DB) -> VideoAsset:
    if not host_allowed(body.source_url.host):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Imports are limited to allow-listed hosts")
    movie = await _load(db, movie_id)
    for a in movie.assets:
        a.is_primary = False
    asset = VideoAsset(movie_id=movie.id, source_url=str(body.source_url), status=AssetStatus.queued)
    db.add(asset)
    await db.flush()
    _enqueue_transcode(asset)
    await db.commit()
    return await _asset(db, asset.id)


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def get_asset(asset_id: uuid.UUID, _: AdminUser, db: DB) -> VideoAsset:
    return await _asset(db, asset_id)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
async def update_asset(asset_id: uuid.UUID, body: AssetPatch, _: AdminUser, db: DB) -> VideoAsset:
    asset = await _asset(db, asset_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    await db.commit()
    return asset


@router.post("/assets/{asset_id}/retry", response_model=AssetOut)
async def retry_asset(asset_id: uuid.UUID, _: AdminUser, db: DB) -> VideoAsset:
    asset = await _asset(db, asset_id)
    if asset.status not in {AssetStatus.failed, AssetStatus.ready}:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Asset is already processing")
    _enqueue_transcode(asset)
    await db.commit()
    return asset


def srt_to_vtt(text: str) -> str:
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text.replace("\r\n", "\n").strip())
    body = re.sub(r"^\d+\n(?=\d{2}:\d{2})", "", body, flags=re.MULTILINE)
    return "WEBVTT\n\n" + body + "\n"


@router.post("/assets/{asset_id}/subtitles", response_model=AssetOut, status_code=201)
async def upload_subtitle(
    asset_id: uuid.UUID,
    _: AdminUser,
    db: DB,
    file: UploadFile = File(...),
    language: str = Form(..., pattern=r"^[a-z]{2}(-[A-Z]{2})?$"),
    label: str = Form(..., min_length=1, max_length=64),
    is_default: bool = Form(False),
) -> VideoAsset:
    asset = await _asset(db, asset_id)
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Subtitle file too large (2MB max)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Subtitles must be UTF-8") from None
    if not text.lstrip().startswith("WEBVTT"):
        if (file.filename or "").lower().endswith(".srt") or re.search(r"\d{2}:\d{2}:\d{2},\d{3} -->", text):
            text = srt_to_vtt(text)
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Upload a .vtt or .srt file")
    sub_id = uuid.uuid4()
    key = f"subtitles/{asset.id}/{sub_id}.{language}.vtt"
    await run_in_threadpool(storage.put_bytes, key, text.encode(), "text/vtt", "private, max-age=3600")
    if is_default:
        for s in asset.subtitles:
            s.is_default = False
    asset.subtitles.append(Subtitle(id=sub_id, language=language, label=label, storage_key=key, is_default=is_default))
    await db.commit()
    return asset


@router.delete("/subtitles/{subtitle_id}", status_code=204)
async def delete_subtitle(subtitle_id: uuid.UUID, _: AdminUser, db: DB) -> None:
    sub = await db.get(Subtitle, subtitle_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subtitle not found")
    await db.delete(sub)
    await db.commit()


# ---------------------------------------------------------------- analytics


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(_: AdminUser, db: DB, days: int = Query(30, ge=1, le=365)) -> AnalyticsOut:
    since = utcnow() - timedelta(days=days)
    in_window = WatchSession.started_at >= since

    views, seconds, viewers = (
        await db.execute(
            select(
                func.count(WatchSession.id),
                func.coalesce(func.sum(WatchSession.seconds_watched), 0),
                func.count(func.distinct(WatchSession.profile_id)),
            ).where(in_window)
        )
    ).one()

    day = func.date(WatchSession.started_at)  # works on Postgres and SQLite
    daily_rows = (
        await db.execute(
            select(day.label("d"), func.count(WatchSession.id), func.coalesce(func.sum(WatchSession.seconds_watched), 0))
            .where(in_window)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    by_day = {str(d): (v, s) for d, v, s in daily_rows}
    today = utcnow().date()
    daily = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        v, s = by_day.get(str(d), (0, 0))
        daily.append(DailyStat(date=d, views=v, watch_minutes=round(s / 60, 1)))

    top_rows = (
        await db.execute(
            select(
                Movie.id, Movie.title, Movie.poster_path,
                func.count(WatchSession.id).label("views"),
                func.coalesce(func.sum(WatchSession.seconds_watched), 0).label("secs"),
            )
            .join(WatchSession, WatchSession.movie_id == Movie.id)
            .where(in_window)
            .group_by(Movie.id, Movie.title, Movie.poster_path)
            .order_by(func.sum(WatchSession.seconds_watched).desc())
            .limit(10)
        )
    ).all()  # fmt: skip

    library_size = await db.scalar(select(func.count()).select_from(Movie).where(Movie.in_library.is_(True))) or 0
    published = await db.scalar(select(func.count()).select_from(Movie).where(catalog.streamable_filter())) or 0
    soon = utcnow() + timedelta(days=30)
    expiring = await db.scalar(
        select(func.count(func.distinct(License.movie_id))).where(License.expires_at > utcnow(), License.expires_at <= soon)
    ) or 0
    processing = await db.scalar(
        select(func.count()).select_from(VideoAsset).where(
            or_(VideoAsset.status == AssetStatus.queued, VideoAsset.status == AssetStatus.downloading,
                VideoAsset.status == AssetStatus.processing)
        )
    ) or 0  # fmt: skip

    return AnalyticsOut(
        days=days,
        views=views,
        watch_hours=round(seconds / 3600, 1),
        unique_viewers=viewers,
        library_size=library_size,
        published=published,
        expiring_soon=expiring,
        processing_jobs=processing,
        daily=daily,
        top_movies=[
            TopMovie(movie_id=mid, title=t, poster_path=p, views=v, watch_minutes=round(s / 60, 1))
            for mid, t, p, v, s in top_rows
        ],
    )
