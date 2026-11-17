"""Playback sessions: authorise a stream, hand out a short-lived token, record progress."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DB, CurrentProfile
from app.api.v1.movies import MOVIE_KEY
from app.core.config import settings
from app.core.rate_limit import RateLimiter
from app.core.security import create_playback_token
from app.core.time import utcnow
from app.models import WatchProgress, WatchSession
from app.schemas.movie import HeartbeatIn, PlaybackOut, PlaybackSubtitle
from app.services import catalog

router = APIRouter(prefix="/playback", tags=["playback"])

COMPLETE_RATIO = 0.92
heartbeat_limiter = RateLimiter(40, 60, scope="heartbeat")


@router.post("/{key}/start", response_model=PlaybackOut)
async def start_playback(
    profile: CurrentProfile, db: DB, key: str = MOVIE_KEY, session_id: uuid.UUID | None = None
) -> PlaybackOut:
    """Authorise playback. Pass `session_id` to renew an expired token without counting a new view."""
    movie = await catalog.get_movie_by_key(db, key)
    availability, asset = await catalog.availability_for(db, movie)
    if movie is None or asset is None or not availability.streamable:
        # Only titles we hold rights to can ever reach this point.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This title is not available to stream")

    session = await db.get(WatchSession, session_id) if session_id else None
    if session is None or session.profile_id != profile.id or session.movie_id != movie.id:
        session = WatchSession(profile_id=profile.id, movie_id=movie.id, asset_id=asset.id, last_heartbeat_at=utcnow())
        db.add(session)
    progress = await db.get(WatchProgress, (profile.id, movie.id))
    resume = 0.0
    if progress and not progress.completed and progress.position_sec > 10:
        resume = max(0.0, progress.position_sec - 3)  # a little pre-roll for context
    await db.commit()

    token = create_playback_token(asset.id, profile.id)
    base = f"{settings.API_V1_PREFIX}/stream/{asset.id}"
    return PlaybackOut(
        session_id=session.id,
        asset_id=asset.id,
        movie=catalog.card_from_movie(movie, True),
        # Direct public-domain sources (archive.org MP4) are played as-is; everything we host
        # goes through tokenised HLS playlists and signed segments.
        master_url=asset.playback_url or f"{base}/master.m3u8?token={token}",
        stream_type="mp4" if asset.playback_url else "hls",
        duration_seconds=asset.duration_seconds,
        resume_position_sec=resume,
        intro_start_sec=asset.intro_start_sec,
        intro_end_sec=asset.intro_end_sec,
        credits_start_sec=asset.credits_start_sec,
        subtitles=[
            PlaybackSubtitle(
                id=s.id,
                language=s.language,
                label=s.label,
                url=f"{base}/subtitles/{s.id}.vtt?token={token}",
                is_default=s.is_default,
            )
            for s in asset.subtitles
        ],
        token_expires_in=settings.PLAYBACK_TOKEN_TTL_SEC,
    )


@router.post("/sessions/{session_id}/heartbeat", status_code=204, dependencies=[Depends(heartbeat_limiter)])
async def heartbeat(session_id: uuid.UUID, body: HeartbeatIn, profile: CurrentProfile, db: DB) -> None:
    session = await db.get(WatchSession, session_id)
    if session is None or session.profile_id != profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    duration = body.duration_sec if body.duration_sec and body.duration_sec > 0 else None
    position = max(0.0, body.position_sec if duration is None else min(body.position_sec, duration))
    delta = min(max(body.watched_delta_sec, 0.0), 120.0)  # never trust the client too much

    completed = bool(duration and position >= duration * COMPLETE_RATIO)
    session.seconds_watched += int(round(delta))
    session.max_position_sec = max(session.max_position_sec or 0.0, position)
    session.last_heartbeat_at = utcnow()
    session.completed = session.completed or completed

    progress = await db.get(WatchProgress, (profile.id, session.movie_id))
    if progress is None:
        progress = WatchProgress(profile_id=profile.id, movie_id=session.movie_id)
        db.add(progress)
    progress.asset_id = session.asset_id
    progress.position_sec = 0.0 if completed else position
    progress.duration_sec = duration or progress.duration_sec
    progress.completed = completed
    progress.updated_at = utcnow()
    await db.commit()
