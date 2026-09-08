"""OEE = Availability x Performance x Quality, computed from floor events.

  Scheduled time = shift calendar intersected with the reporting window
  Loading time   = scheduled time - planned stops
  Run time       = loading time - unplanned stops
  Availability   = run time / loading time
  Performance    = (ideal cycle x total units) / run time
  Quality        = good units / total units

Everything is derived from the same confirmations and downtime events the
operators enter, so the number can always be traced back to its evidence.
"""
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.equipment import DowntimeEvent, DowntimeReason, Machine
from ..models.production import Confirmation, OrderOperation
from . import calendar_service


@dataclass
class OeeResult:
    machine_id: int
    machine_code: str
    machine_name: str
    window_start: datetime
    window_end: datetime
    scheduled_minutes: float
    planned_downtime_minutes: float
    unplanned_downtime_minutes: float
    loading_minutes: float
    run_minutes: float
    good_count: float
    scrap_count: float
    total_count: float
    availability: float
    performance: float
    quality: float
    oee: float

    def as_dict(self) -> dict:
        return asdict(self)


def scheduled_minutes(db: Session, window_start: datetime, window_end: datetime) -> float:
    """Minutes the plant was rostered to produce inside the reporting window.

    Delegates to the shared shift calendar so OEE and the scheduler can never
    disagree about when the plant is open.
    """
    return calendar_service.scheduled_minutes(
        calendar_service.shift_windows(db, window_start, window_end)
    )


def _overlap_minutes(start: datetime, end: datetime, window_start: datetime, window_end: datetime) -> float:
    """Minutes of [start, end) that fall inside the reporting window."""
    lo = max(start, window_start)
    hi = min(end or window_end, window_end)
    return max((hi - lo).total_seconds() / 60.0, 0.0)


def calculate_oee(db: Session, machine: Machine, window_start: datetime, window_end: datetime) -> OeeResult:
    scheduled = scheduled_minutes(db, window_start, window_end)

    planned = 0.0
    unplanned = 0.0
    events = db.execute(
        select(DowntimeEvent, DowntimeReason)
        .join(DowntimeReason, DowntimeEvent.reason_id == DowntimeReason.id)
        .where(
            DowntimeEvent.machine_id == machine.id,
            DowntimeEvent.started_at < window_end,
            # An open event (ended_at IS NULL) is still running now.
            (DowntimeEvent.ended_at.is_(None)) | (DowntimeEvent.ended_at > window_start),
        )
    ).all()
    for event, reason in events:
        minutes = _overlap_minutes(event.started_at, event.ended_at, window_start, window_end)
        if reason.affects_availability:
            unplanned += minutes
        else:
            planned += minutes

    loading = max(scheduled - planned, 0.0)
    run = max(loading - unplanned, 0.0)

    good, scrap = db.execute(
        select(
            func.coalesce(func.sum(Confirmation.qty_good), 0.0),
            func.coalesce(func.sum(Confirmation.qty_scrap), 0.0),
        )
        .join(OrderOperation, Confirmation.operation_id == OrderOperation.id)
        .where(
            OrderOperation.machine_id == machine.id,
            Confirmation.ended_at >= window_start,
            Confirmation.ended_at <= window_end,
        )
    ).one()
    good = float(good or 0.0)
    scrap = float(scrap or 0.0)
    total = good + scrap

    availability = run / loading if loading > 0 else 0.0
    ideal_minutes = machine.ideal_cycle_seconds * total / 60.0
    performance = min(ideal_minutes / run, 1.0) if run > 0 else 0.0
    quality = good / total if total > 0 else 0.0

    return OeeResult(
        machine_id=machine.id,
        machine_code=machine.code,
        machine_name=machine.name,
        window_start=window_start,
        window_end=window_end,
        scheduled_minutes=round(scheduled, 1),
        planned_downtime_minutes=round(planned, 1),
        unplanned_downtime_minutes=round(unplanned, 1),
        loading_minutes=round(loading, 1),
        run_minutes=round(run, 1),
        good_count=good,
        scrap_count=scrap,
        total_count=total,
        availability=round(availability, 4),
        performance=round(performance, 4),
        quality=round(quality, 4),
        oee=round(availability * performance * quality, 4),
    )


def plant_oee(db: Session, window_start: datetime, window_end: datetime) -> list[OeeResult]:
    machines = db.scalars(select(Machine).where(Machine.is_active.is_(True)).order_by(Machine.code)).all()
    return [calculate_oee(db, m, window_start, window_end) for m in machines]


def downtime_pareto(
    db: Session,
    window_start: datetime,
    window_end: datetime,
    limit: int = 8,
    include_planned: bool = False,
) -> list[dict]:
    """Losses ranked biggest-first - where to send the improvement team.

    Planned stops are excluded by default. They are real minutes, but they are
    not machine losses, and leaving them in lets "no work scheduled" swamp every
    genuine problem on the chart.
    """
    rows = db.execute(
        select(
            DowntimeReason.code,
            DowntimeReason.name,
            DowntimeReason.category,
            func.count(DowntimeEvent.id),
            func.coalesce(func.sum(DowntimeEvent.duration_minutes), 0.0),
        )
        .join(DowntimeEvent, DowntimeEvent.reason_id == DowntimeReason.id)
        .where(
            DowntimeEvent.started_at >= window_start,
            DowntimeEvent.started_at <= window_end,
            *([] if include_planned else [DowntimeReason.affects_availability.is_(True)]),
        )
        .group_by(DowntimeReason.id)
        .order_by(func.sum(DowntimeEvent.duration_minutes).desc())
        .limit(limit)
    ).all()
    return [
        {
            "code": code,
            "name": name,
            "category": category,
            "events": events,
            "minutes": round(float(minutes or 0.0), 1),
        }
        for code, name, category, events, minutes in rows
    ]
