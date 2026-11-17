import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenError, decode_token
from app.models import Profile, User
from app.services.tmdb import TMDBClient

ACCESS_COOKIE = "cv_access"
REFRESH_COOKIE = "cv_refresh"
PROFILE_COOKIE = "cv_profile"

DB = Annotated[AsyncSession, Depends(get_db)]


def get_tmdb(request: Request) -> TMDBClient:
    return request.app.state.tmdb


TMDB = Annotated[TMDBClient, Depends(get_tmdb)]


def _bearer_or_cookie(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


async def get_optional_user(request: Request, db: DB) -> User | None:
    token = _bearer_or_cookie(request)
    if not token:
        return None
    try:
        payload = decode_token(token, "access")
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError):
        return None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def get_current_profile(
    request: Request, user: Annotated[User, Depends(get_current_user)], db: DB
) -> Profile:
    requested = request.headers.get("x-profile-id") or request.cookies.get(PROFILE_COOKIE)
    profiles = list(
        await db.scalars(select(Profile).where(Profile.user_id == user.id).order_by(Profile.created_at))
    )
    if not profiles:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Create a profile first")
    if requested:
        for p in profiles:
            if str(p.id) == requested:
                return p
    return profiles[0]


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]
CurrentProfile = Annotated[Profile, Depends(get_current_profile)]
