"""Shift calendar - defines when the plant is scheduled to produce.

OEE is meaningless without this. Availability must be measured against the time
the plant intended to run, not against wall-clock time: a line that is idle on a
Sunday has not lost anything.

Times are stored as minutes from midnight rather than TIME columns so an
overnight shift (end <= start, meaning it crosses midnight) is plain arithmetic
rather than a special case in every query.
"""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    start_minute: Mapped[int] = mapped_column(Integer, default=8 * 60)
    end_minute: Mapped[int] = mapped_column(Integer, default=17 * 60)
    # Seven characters, Monday first: "1111100" is a five-day week.
    weekdays: Mapped[str] = mapped_column(String(7), default="1111100")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def crosses_midnight(self) -> bool:
        return self.end_minute <= self.start_minute

    @property
    def length_minutes(self) -> int:
        span = self.end_minute - self.start_minute
        return span + 24 * 60 if span <= 0 else span
