"""Database engine, session factory and declarative base."""
import logging
from collections.abc import Iterator
from datetime import datetime

from enum import Enum as PyEnum

from sqlalchemy import DateTime, String, TypeDecorator, create_engine, event, func, inspect, text
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


def sync_new_columns() -> None:
    """Add model columns that an existing database file does not have yet.

    ``create_all`` creates missing *tables* but never missing *columns*, so a
    new nullable field would otherwise raise "no such column" against a
    database seeded before it existed. This closes that gap for the sample
    plant; the multi-site rollout should switch to Alembic, which also handles
    the cases deliberately skipped here (non-nullable columns, renames, type
    changes).
    """
    logger = logging.getLogger("ipms")
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all() will build it in full
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            # Only additions that are safe to backfill with NULL. Anything else
            # needs a real migration with a considered default.
            if not column.nullable or column.primary_key:
                logger.warning(
                    "Column %s.%s is missing and cannot be added automatically - reseed or migrate.",
                    table.name,
                    column.name,
                )
                continue
            ddl = column.type.compile(engine.dialect)
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl}"))
            logger.info("Added missing column %s.%s", table.name, column.name)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
