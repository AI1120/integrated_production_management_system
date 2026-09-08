"""Shared FastAPI dependencies: DB session, current user, role gates."""
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..enums import Role
from ..models.user import User
from ..security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Depends(get_db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired - please sign in again")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user = db.get(User, payload.get("uid"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is inactive or unknown")
    return user


def require_roles(*roles: Role) -> Callable[[User], User]:
    """Gate an endpoint behind one or more roles. ADMIN always passes."""
    allowed = set(roles) | {Role.ADMIN}

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role {user.role} may not perform this action.",
            )
        return user

    return _guard


CurrentUser = Depends(get_current_user)
