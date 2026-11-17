import uuid
from datetime import timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.time import utcnow

TokenType = Literal["access", "refresh", "playback"]

_hasher = PasswordHasher()
# Used to equalise timing when a login email does not exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


class TokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def _encode(claims: dict[str, Any], ttl: timedelta) -> str:
    now = utcnow()
    payload = {**claims, "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, is_admin: bool) -> str:
    return _encode(
        {"sub": str(user_id), "typ": "access", "adm": is_admin},
        timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN),
    )


def create_refresh_token(user_id: uuid.UUID, jti: uuid.UUID, family: uuid.UUID) -> str:
    return _encode(
        {"sub": str(user_id), "typ": "refresh", "jti": str(jti), "fam": str(family)},
        timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )


def create_playback_token(asset_id: uuid.UUID, profile_id: uuid.UUID) -> str:
    return _encode(
        {"sub": str(profile_id), "typ": "playback", "aid": str(asset_id)},
        timedelta(seconds=settings.PLAYBACK_TOKEN_TTL_SEC),
    )


def decode_token(token: str, expected: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("typ") != expected:
        raise TokenError("wrong token type")
    return payload
