from pydantic import BaseModel, Field

from ..enums import Role
from .common import ORMModel


class LoginRequest(BaseModel):
    username: str
    password: str


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


class UserCreate(UserBase):
    password: str = Field(min_length=4)


class UserUpdate(BaseModel):
    full_name: str | None = None
    badge_no: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4)


class UserRead(UserBase, ORMModel):
    id: int


Token.model_rebuild()
