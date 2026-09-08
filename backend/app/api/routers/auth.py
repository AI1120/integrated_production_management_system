from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...enums import Role
from ...models.user import User
from pydantic import BaseModel, Field

from ...schemas.auth import LoginRequest, Token, UserCreate, UserRead, UserUpdate
from ...security import create_access_token, hash_password, verify_password
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")

    token = create_access_token(subject=user.username, role=user.role, user_id=user.id)
    return Token(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> User:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Username {payload.username} already exists")

    data = payload.model_dump(exclude={"password"})
    user = User(**data, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=4)


def _active_admins(db: Session, excluding: int | None = None) -> int:
    stmt = select(User).where(User.role == Role.ADMIN, User.is_active.is_(True))
    if excluding is not None:
        stmt = stmt.where(User.id != excluding)
    return len(list(db.scalars(stmt)))


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    data = payload.model_dump(exclude_unset=True)

    # Two ways an administrator can lock the plant out of its own system, both
    # worth refusing rather than explaining afterwards.
    losing_admin = (
        data.get("is_active") is False or (data.get("role") is not None and data["role"] != Role.ADMIN)
    )
    if user.role == Role.ADMIN and losing_admin:
        if user.id == actor.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "You cannot remove your own administrator access. Ask another administrator.",
            )
        if _active_admins(db, excluding=user.id) == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This is the last active administrator. Promote someone else first.",
            )

    if password := data.pop("password", None):
        user.password_hash = hash_password(password)
    for field, value in data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.post("/me/password", response_model=UserRead)
def change_own_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """Anyone may change their own password, given the current one."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return user
