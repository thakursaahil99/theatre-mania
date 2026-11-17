import uuid
from datetime import timedelta

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ACCESS_COOKIE, PROFILE_COOKIE, REFRESH_COOKIE
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.core.time import utcnow
from app.models import Profile, RefreshToken, User

REFRESH_PATH = f"{settings.API_V1_PREFIX}/auth"
SESSION_MARKER_COOKIE = "cv_session"


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "domain": settings.COOKIE_DOMAIN,
    }


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    refresh_age = settings.REFRESH_TOKEN_TTL_DAYS * 86400
    response.set_cookie(ACCESS_COOKIE, access, max_age=settings.ACCESS_TOKEN_TTL_MIN * 60, path="/", **_cookie_kwargs())
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=refresh_age, path=REFRESH_PATH, **_cookie_kwargs())
    # Non-secret marker visible on every path so the frontend middleware can tell
    # "signed in (maybe needs a refresh)" from "signed out" without seeing the refresh token.
    response.set_cookie(SESSION_MARKER_COOKIE, "1", max_age=refresh_age, path="/", **_cookie_kwargs())


def set_profile_cookie(response: Response, profile_id: uuid.UUID) -> None:
    response.set_cookie(
        PROFILE_COOKIE, str(profile_id), max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400, path="/", **_cookie_kwargs()
    )


def clear_auth_cookies(response: Response) -> None:
    kw = {"domain": settings.COOKIE_DOMAIN, "secure": settings.COOKIE_SECURE, "httponly": True,
          "samesite": settings.COOKIE_SAMESITE}
    response.delete_cookie(ACCESS_COOKIE, path="/", **kw)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, **kw)
    response.delete_cookie(PROFILE_COOKIE, path="/", **kw)
    response.delete_cookie(SESSION_MARKER_COOKIE, path="/", **kw)


async def issue_session(
    db: AsyncSession, response: Response, user: User, user_agent: str | None, family: uuid.UUID | None = None
) -> None:
    jti = uuid.uuid4()
    family = family or uuid.uuid4()
    db.add(
        RefreshToken(
            id=jti,
            user_id=user.id,
            family_id=family,
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    user.last_login_at = utcnow()
    set_auth_cookies(response, create_access_token(user.id, user.is_admin), create_refresh_token(user.id, jti, family))


async def revoke_family(db: AsyncSession, family: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def default_profile_name(user: User) -> str:
    base = (user.display_name or user.email.split("@")[0]).strip()
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in " .'-_")[:30]
    return cleaned or "Me"


async def create_user(
    db: AsyncSession,
    email: str,
    password: str | None,
    display_name: str | None = None,
    google_sub: str | None = None,
    email_verified: bool = False,
) -> User:
    email = email.lower()
    user = User(
        email=email,
        password_hash=hash_password(password) if password else None,
        display_name=display_name,
        google_sub=google_sub,
        email_verified=email_verified,
        is_admin=email in settings.admin_emails,
    )
    user.profiles = [Profile(name=default_profile_name(user), avatar="nebula")]
    db.add(user)
    await db.flush()
    return user


async def get_or_create_google_user(db: AsyncSession, info: dict) -> User:
    sub, email = info["sub"], info.get("email", "").lower()
    user = await db.scalar(select(User).where(User.google_sub == sub))
    if user:
        return user
    if email and info.get("email_verified"):
        # Link to an existing password account only when Google has verified the address.
        user = await db.scalar(select(User).where(User.email == email))
        if user:
            user.google_sub = sub
            user.email_verified = True
            return user
    if not email:
        raise ValueError("Google account has no email")
    if await db.scalar(select(User.id).where(User.email == email)):
        raise ValueError("Email already registered; sign in with your password")
    return await create_user(
        db, email, None, display_name=info.get("name"), google_sub=sub, email_verified=bool(info.get("email_verified"))
    )
