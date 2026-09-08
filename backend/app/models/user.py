from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base, EnumString, TimestampMixin
from ..enums import Role


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    # Badge / ID card number - scanned at the operator terminal to identify the worker.
    badge_no: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, default=None)
    role: Mapped[Role] = mapped_column(EnumString(Role, 20), default=Role.OPERATOR)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Stamped on every successful sign-in, so an administrator can spot the
    # accounts nobody has used since the plant went live.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
