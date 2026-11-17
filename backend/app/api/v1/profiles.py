import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.models import Profile
from app.schemas.profile import ProfileCreate, ProfileOut, ProfileUpdate
from app.services.auth import set_profile_cookie

router = APIRouter(prefix="/profiles", tags=["profiles"])


async def _own_profile(db: DB, user_id: uuid.UUID, profile_id: uuid.UUID) -> Profile:
    profile = await db.get(Profile, profile_id)
    if profile is None or profile.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.get("", response_model=list[ProfileOut])
async def list_profiles(user: CurrentUser, db: DB) -> list[Profile]:
    return list(await db.scalars(select(Profile).where(Profile.user_id == user.id).order_by(Profile.created_at)))


@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(body: ProfileCreate, user: CurrentUser, db: DB) -> Profile:
    count = await db.scalar(select(func.count()).select_from(Profile).where(Profile.user_id == user.id))
    if (count or 0) >= settings.MAX_PROFILES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"You can have up to {settings.MAX_PROFILES} profiles")
    profile = Profile(user_id=user.id, name=body.name.strip(), avatar=body.avatar, is_kids=body.is_kids)
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A profile with that name already exists") from None
    return profile


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(profile_id: uuid.UUID, body: ProfileUpdate, user: CurrentUser, db: DB) -> Profile:
    profile = await _own_profile(db, user.id, profile_id)
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(profile, field, value.strip() if isinstance(value, str) and field == "name" else value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A profile with that name already exists") from None
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    profile = await _own_profile(db, user.id, profile_id)
    count = await db.scalar(select(func.count()).select_from(Profile).where(Profile.user_id == user.id))
    if (count or 0) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="You need at least one profile")
    await db.delete(profile)
    await db.commit()


@router.post("/{profile_id}/select", response_model=ProfileOut)
async def select_profile(profile_id: uuid.UUID, user: CurrentUser, db: DB, response: Response) -> Profile:
    profile = await _own_profile(db, user.id, profile_id)
    set_profile_cookie(response, profile.id)
    return profile
