from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..enums import Role
from .common import ORMModel


def _blank_to_none(value: str | None) -> str | None:
    """Treat a cleared form field as "no badge" rather than an empty string.

    badge_no is unique, so several people saved with "" would collide on the
    second one - and the collision would read as a duplicate badge, which is
    not what happened.
    """
    if value is None:
        return None
    return value.strip() or None


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _normalise_username(cls, value: str) -> str:
        # Accounts are stored lower-cased, and a terminal keyboard will happily
        # capitalise the first letter for an operator wearing gloves.
        return value.strip().lower()


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserRead"


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str
    badge_no: str | None = None
    role: Role = Role.OPERATOR
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def _normalise_username(cls, value: str) -> str:
        # Sign-in looks the username up verbatim, so "Admin" and "admin" would
        # be two accounts of which only one can ever log in.
        return value.strip().lower()

    @field_validator("full_name")
    @classmethod
    def _trim_full_name(cls, value: str) -> str:
        return value.strip()

    _clean_badge = field_validator("badge_no")(_blank_to_none)


class UserCreate(UserBase):
    password: str = Field(min_length=4)


class UserUpdate(BaseModel):
    full_name: str | None = None
    badge_no: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4)

    _clean_badge = field_validator("badge_no")(_blank_to_none)


class UserRead(UserBase, ORMModel):
    id: int
    last_login_at: datetime | None = None


Token.model_rebuild()
