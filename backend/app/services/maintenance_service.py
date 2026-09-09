"""Preventive maintenance: when a machine is next due a stop, and when it is
therefore not available to be loaded with work.

The shift calendar answers "when is the plant open". It cannot answer "is this
particular machine able to run", and until now nothing did - the scheduler
picked machines on timing alone, so a job could be planned onto a machine that
was standing broken or was about to be taken out for a service. This module is
the missing half, and it deliberately speaks in the same shift windows the
scheduler and OEE already use, so the three cannot drift apart.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import MachineStatus
from ..models.equipment import MaintenancePlan, Machine
from . import calendar_service as cal

Window = tuple[datetime, datetime]

# A machine cannot be stopped for maintenance more often than this many times
# inside one horizon. Purely a guard against a plan configured with a silly
# interval generating work forever.
MAX_STOPS_PER_PLAN = 24

STOPPED_STATES = {MachineStatus.DOWN, MachineStatus.MAINTENANCE}


def next_due_at(plan: MaintenancePlan) -> datetime:
    """When this plan is next due.

    Measured from the last time it was actually done; from the day the plan was
    written when it has never been done, so a new plan comes due one interval
    later rather than immediately.
    """
    base = plan.last_done_at or plan.created_at or datetime.now()
    return base + timedelta(days=plan.interval_days)


def planned_stops(
    plan: MaintenancePlan,
    windows: list[Window],
    frm: datetime,
    to: datetime,
) -> list[Window]:
    """The slots this plan reserves on its machine inside [frm, to).

    Maintenance consumes production time like any other work, so it is placed
    with the same ``place_work`` the scheduler uses: it lands inside a shift and
    spans a shift boundary rather than pretending to happen overnight. An
    overdue plan is placed at the next opening rather than in the past.
    """
    stops: list[Window] = []
    due = max(next_due_at(plan), frm)

    while due < to and len(stops) < MAX_STOPS_PER_PLAN:
        slot = cal.place_work(windows, due, plan.duration_minutes)
        if slot is None:
            break  # the horizon ran out before the stop fitted
        stops.append(slot)
        # The next service is due an interval after this one is finished, not
        # an interval after it was due - a late service moves the ones after it.
        due = slot[1] + timedelta(days=plan.interval_days)

    return stops


def active_plans(db: Session) -> dict[int, list[MaintenancePlan]]:
    """Active maintenance plans, grouped by the machine they belong to."""
    plans = db.scalars(select(MaintenancePlan).where(MaintenancePlan.is_active.is_(True)))
    grouped: dict[int, list[MaintenancePlan]] = {}
    for plan in plans:
        grouped.setdefault(plan.machine_id, []).append(plan)
    return grouped


def assumed_return(windows: list[Window], frm: datetime) -> datetime:
    """How long a stop with no estimate is assumed to last: the rest of the shift.

    Some answer has to be picked, and both extremes are wrong. Assuming the
    machine is back immediately is what let work be planned onto a machine
    standing broken. Assuming it is gone for the whole horizon is worse in
    practice - breakdowns are routine, and one unestimated stop would empty the
    entire schedule rather than shift a few hours of work.

    The rest of the current shift is the honest middle: it costs the machine the
    time it is visibly not running, and asks the planner to set an expected
    return for anything longer. A machine stopped outside production hours
    reserves nothing, because nothing was going to run on it anyway.
    """
    for start, end in windows:
        if start <= frm < end:
            return end
    return frm


def unavailable_blocks(
    machine: Machine,
    plans: list[MaintenancePlan],
    windows: list[Window],
    frm: datetime,
    to: datetime,
) -> list[Window]:
    """Everything keeping this machine from taking work in [frm, to).

    Two sources, and the difference matters:

      * it is stopped right now - blocked until it is expected back, or, when
        nobody has estimated that, until the end of the current shift.
      * it is due preventive maintenance inside the horizon.
    """
    blocks: list[Window] = []

    if machine.status in STOPPED_STATES:
        back = machine.available_from or assumed_return(windows, frm)
        if back > frm:
            blocks.append((frm, min(back, to)))

    for plan in plans:
        blocks.extend(planned_stops(plan, windows, frm, to))

    return blocks


def machine_windows(
    db: Session,
    machines: list[Machine],
    windows: list[Window],
    frm: datetime,
    to: datetime,
) -> dict[int, list[Window]]:
    """Loadable time per machine: the plant's shifts, less that machine's stops."""
    plans = active_plans(db)
    return {
        machine.id: cal.subtract(
            windows, unavailable_blocks(machine, plans.get(machine.id, []), windows, frm, to)
        )
        for machine in machines
    }


def due_report(db: Session, *, within_days: int = 14) -> list[dict]:
    """Plans due, or overdue, within the next ``within_days``.

    The list a maintenance planner works from, worst first.
    """
    now = datetime.now()
    horizon = now + timedelta(days=within_days)
    rows: list[dict] = []

    for plan in db.scalars(
        select(MaintenancePlan).where(MaintenancePlan.is_active.is_(True))
    ):
        due = next_due_at(plan)
        if due > horizon:
            continue
        rows.append(
            {
                "plan_id": plan.id,
                "machine_id": plan.machine_id,
                "machine_code": plan.machine.code,
                "machine_name": plan.machine.name,
                "name": plan.name,
                "interval_days": plan.interval_days,
                "duration_minutes": plan.duration_minutes,
                "last_done_at": plan.last_done_at,
                "next_due_at": due,
                "days_until_due": round((due - now).total_seconds() / 86400.0, 2),
                "is_overdue": due < now,
            }
        )

    rows.sort(key=lambda row: row["next_due_at"])
    return rows
