from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for every response schema read straight off a SQLAlchemy row."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    detail: str


def to_local_naive(value: datetime | None) -> datetime | None:
    """Convert an offset-aware instant to this plant's wall clock.

    Every timestamp here is stored naive and read back as local time, so a
    client sending "...Z" would otherwise have its UTC wall clock stored
    verbatim - moving a plan by the whole UTC offset, and rolling an evening
    finish past midnight onto the following day. Naive input is already local
    and passes through untouched.
    """
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)
