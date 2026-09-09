"""Shift calendar arithmetic.

One implementation of "when is the plant actually open", used by both OEE
(how much time did we intend to run?) and the scheduler (when can this job
actually be worked?). Two answers to that question would let the reported
utilisation disagree with the schedule that produced it.
"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.shift import Shift

Window = tuple[datetime, datetime]


def shift_windows(db: Session, frm: datetime, to: datetime) -> list[Window]:
    """Every production interval overlapping [frm, to), in chronological order.

    With no shift calendar configured the plant is treated as continuously
    available, so a fresh install still schedules rather than refusing to.
    """
    if to <= frm:
        return []

    shifts = list(db.scalars(select(Shift).where(Shift.is_active.is_(True))))
    if not shifts:
        return [(frm, to)]

    windows: list[Window] = []
    # Start a day early so an overnight shift begun before `frm` is included.
    day: date = (frm - timedelta(days=1)).date()
    last_day: date = to.date()
    while day <= last_day:
        midnight = datetime.combine(day, time())
        for shift in shifts:
            if shift.weekdays[day.weekday()] != "1":
                continue
            start = midnight + timedelta(minutes=shift.start_minute)
            end = start + timedelta(minutes=shift.length_minutes)
            lo, hi = max(start, frm), min(end, to)
            if hi > lo:
                windows.append((lo, hi))
        day += timedelta(days=1)

    windows.sort()
    return _merge(windows)


def _merge(windows: list[Window]) -> list[Window]:
    """Collapse overlapping shifts so no minute is ever counted twice."""
    merged: list[Window] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract(windows: list[Window], blocks: list[Window]) -> list[Window]:
    """Production time with ``blocks`` taken out of it.

    A shift calendar says when the *plant* is open; it cannot say when one
    machine is unavailable. Subtracting a machine's own stoppages - a
    maintenance slot, a breakdown it has not come back from - gives the time
    the scheduler may actually load that machine, using the same window
    arithmetic as everything else.
    """
    remaining = [w for w in windows if w[1] > w[0]]
    for block_start, block_end in blocks:
        if block_end <= block_start:
            continue
        trimmed: list[Window] = []
        for start, end in remaining:
            if block_end <= start or block_start >= end:
                trimmed.append((start, end))
                continue
            if start < block_start:
                trimmed.append((start, block_start))
            if block_end < end:
                trimmed.append((block_end, end))
        remaining = trimmed
    return remaining


def scheduled_minutes(windows: list[Window]) -> float:
    return sum((end - start).total_seconds() / 60.0 for start, end in windows)


def place_work(windows: list[Window], earliest: datetime, minutes: float) -> Window | None:
    """Fit ``minutes`` of work in, starting no earlier than ``earliest``.

    Work spans shift boundaries: a 6-hour job started at 16:00 on a Friday
    finishes on Monday morning, not at 22:00 on the Friday. Returns None when
    the horizon runs out before the work fits.
    """
    if minutes <= 0:
        start = next_open(windows, earliest)
        return (start, start) if start else None

    remaining = minutes
    start: datetime | None = None

    for window_start, window_end in windows:
        segment_start = max(window_start, earliest)
        if segment_start >= window_end:
            continue
        if start is None:
            start = segment_start
        available = (window_end - segment_start).total_seconds() / 60.0
        if available >= remaining - 1e-9:
            return start, segment_start + timedelta(minutes=remaining)
        remaining -= available

    return None


def next_open(windows: list[Window], at: datetime) -> datetime | None:
    """The first moment production is possible at or after ``at``."""
    for window_start, window_end in windows:
        if window_end <= at:
            continue
        return max(window_start, at)
    return None


def working_minutes_between(windows: list[Window], frm: datetime, to: datetime) -> float:
    """Production minutes between two instants - the honest measure of elapsed
    time on a shop floor, where 16 hours of a weekend are not 16 hours of delay."""
    if to <= frm:
        return 0.0
    total = 0.0
    for window_start, window_end in windows:
        lo, hi = max(window_start, frm), min(window_end, to)
        if hi > lo:
            total += (hi - lo).total_seconds() / 60.0
    return total
