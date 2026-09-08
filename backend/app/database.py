"""Database engine, session factory and declarative base."""
from collections.abc import Iterator
from datetime import datetime

from enum import Enum as PyEnum

from sqlalchemy import DateTime, String, TypeDecorator, create_engine, event, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=settings.sql_echo, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


class EnumString(TypeDecorator):
    """Store an enum as a plain VARCHAR but hand back the enum member on load.

    A bare ``String`` column returns ``str``, which quietly breaks ``is``
    comparisons against the enum. Keeping the column a plain VARCHAR (rather
    than a native DB enum) also means adding a status value later is a code
    change, not a migration on a live table.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[PyEnum], length: int = 30, **kwargs):
        self.enum_class = enum_class
        super().__init__(length=length, **kwargs)

    def process_bind_param(self, value, _dialect):
        if value is None:
            return None
        return value.value if isinstance(value, PyEnum) else str(value)

    def process_result_value(self, value, _dialect):
        return None if value is None else self.enum_class(value)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Audit columns every transactional table carries."""

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
