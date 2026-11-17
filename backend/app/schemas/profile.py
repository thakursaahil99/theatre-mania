import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Keys map to illustrated avatars shipped with the frontend (public/avatars/<key>.svg).
Avatar = Literal[
    "nebula", "ember", "aurora", "noir", "neon", "solar", "tide", "orchid",
    "volt", "frost", "dune", "rose",
]


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=30, pattern=r"^[\w .'\-]+$")
    avatar: Avatar = "nebula"
    is_kids: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30, pattern=r"^[\w .'\-]+$")
    avatar: Avatar | None = None
    is_kids: bool | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    avatar: str
    is_kids: bool
