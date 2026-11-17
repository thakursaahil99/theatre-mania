import base64
import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DB, PROFILE_COOKIE, REFRESH_COOKIE, CurrentUser
from app.core.config import settings
from app.core.rate_limit import auth_limiter
from app.core.security import TokenError, decode_token, verify_password
from app.core.time import as_aware, utcnow
from app.models import Profile, RefreshToken, User
from app.schemas.auth import LoginIn, SessionOut, SignupIn, UserOut
from app.services.auth import (
    clear_auth_cookies,
    create_user,
    get_or_create_google_user,
    issue_session,
    revoke_family,
    set_profile_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_COOKIE = "cv_oauth"
OAUTH_COOKIE_PATH = f"{settings.API_V1_PREFIX}/auth/google"


async def _session_out(db: DB, user: User, request: Request) -> SessionOut:
    active = request.cookies.get(PROFILE_COOKIE)
    profile_ids = [str(p) for p in await db.scalars(select(Profile.id).where(Profile.user_id == user.id))]
    return SessionOut(
        user=UserOut.model_validate(user),
        active_profile_id=uuid.UUID(active) if active in profile_ids else None,
    )


@router.post("/signup", response_model=SessionOut, status_code=201, dependencies=[Depends(auth_limiter)])
async def signup(body: SignupIn, request: Request, response: Response, db: DB) -> SessionOut:
    if await db.scalar(select(User.id).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = await create_user(db, body.email, body.password, body.display_name)
    await issue_session(db, response, user, request.headers.get("user-agent"))
    set_profile_cookie(response, user.profiles[0].id)
    await db.commit()
    return SessionOut(user=UserOut.model_validate(user), active_profile_id=user.profiles[0].id)


@router.post("/login", response_model=SessionOut, dependencies=[Depends(auth_limiter)])
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> SessionOut:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not verify_password(body.password, user.password_hash if user else None) or not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    await issue_session(db, response, user, request.headers.get("user-agent"))
    await db.commit()
    return await _session_out(db, user, request)


@router.post("/refresh", response_model=SessionOut)
async def refresh(request: Request, response: Response, db: DB) -> SessionOut:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    try:
        payload = decode_token(token, "refresh")
        jti, family = uuid.UUID(payload["jti"]), uuid.UUID(payload["fam"])
    except (TokenError, KeyError, ValueError):
        clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None

    record = await db.get(RefreshToken, jti)
    if record is None or as_aware(record.expires_at) <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if record.revoked_at is not None:
        # A rotated token was replayed: assume theft and kill the whole session family.
        await revoke_family(db, family)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session revoked")

    user = await db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
    record.revoked_at = utcnow()
    await issue_session(db, response, user, request.headers.get("user-agent"), family=family)
    await db.commit()
    return await _session_out(db, user, request)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DB) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            payload = decode_token(token, "refresh")
            await revoke_family(db, uuid.UUID(payload["fam"]))
            await db.commit()
        except (TokenError, KeyError, ValueError):
            pass
    clear_auth_cookies(response)


@router.get("/me", response_model=SessionOut)
async def me(user: CurrentUser, request: Request, db: DB) -> SessionOut:
    return await _session_out(db, user, request)


# ------------------------------------------------------------------ Google OAuth (PKCE)


@router.get("/google/login", include_in_schema=True)
async def google_login(next: str = "/profiles") -> RedirectResponse:
    if not settings.google_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Google sign-in is not configured")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/profiles"
    sealed = jwt.encode(
        {"state": state, "verifier": verifier, "next": safe_next, "exp": utcnow() + timedelta(minutes=10)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    resp.set_cookie(
        OAUTH_COOKIE, sealed, max_age=600, path=OAUTH_COOKIE_PATH, httponly=True,
        secure=settings.COOKIE_SECURE, samesite="lax",
    )
    return resp


@router.get("/google/callback", include_in_schema=False)
async def google_callback(request: Request, db: DB, code: str | None = None, state: str | None = None):
    fail = RedirectResponse(f"{settings.FRONTEND_URL}/login?error=oauth", status_code=302)
    sealed = request.cookies.get(OAUTH_COOKIE)
    if not (code and state and sealed and settings.google_enabled):
        return fail
    try:
        stash = jwt.decode(sealed, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return fail
    if not secrets.compare_digest(stash.get("state", ""), state):
        return fail

    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": stash["verifier"],
            },
        )
        if token_resp.status_code != 200:
            return fail
        info_resp = await client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"}
        )
        if info_resp.status_code != 200:
            return fail
        info = info_resp.json()

    try:
        user = await get_or_create_google_user(db, info)
    except ValueError:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=email_in_use", status_code=302)
    if not user.is_active:
        return fail

    resp = RedirectResponse(f"{settings.FRONTEND_URL}{stash.get('next', '/profiles')}", status_code=302)
    await issue_session(db, resp, user, request.headers.get("user-agent"))
    await db.commit()
    resp.delete_cookie(OAUTH_COOKIE, path=OAUTH_COOKIE_PATH)
    return resp
