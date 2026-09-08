"""Machines, downtime capture, maintenance requests and OEE."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...enums import MachineStatus, Role
from ...models.equipment import DowntimeEvent, DowntimeReason, Machine, MaintenanceRequest
from ...models.user import User
from ...schemas.equipment import (
    DowntimeEnd,
    DowntimeEventRead,
    DowntimeReasonCreate,
    DowntimeReasonRead,
    DowntimeStart,
    MachineCreate,
    MachineRead,
    MachineStatusUpdate,
    MaintenanceRequestCreate,
    MaintenanceRequestRead,
    OeeRead,
)
from ...services import oee_service
from ...services.numbering import next_number
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/equipment", tags=["equipment"])

Maintainer = Depends(require_roles(Role.OPERATOR, Role.PLANNER))
AnyUser = Depends(get_current_user)


def _window(days: int, hours: int | None) -> tuple[datetime, datetime]:
    end = datetime.now()
    start = end - (timedelta(hours=hours) if hours else timedelta(days=days))
    return start, end


# --- Machines ---------------------------------------------------------------
@router.get("/machines", response_model=list[MachineRead])
def list_machines(db: Session = Depends(get_db), _: User = AnyUser) -> list[Machine]:
    return list(
        db.scalars(select(Machine).options(selectinload(Machine.work_center)).order_by(Machine.code))
    )


@router.post("/machines", response_model=MachineRead, status_code=status.HTTP_201_CREATED)
def create_machine(
    payload: MachineCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.PLANNER))
) -> Machine:
    if db.scalar(select(Machine).where(Machine.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Machine {payload.code} already exists")
    machine = Machine(**payload.model_dump(), status_since=datetime.now())
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


@router.post("/machines/{machine_id}/status", response_model=MachineRead)
def set_machine_status(
    machine_id: int,
    payload: MachineStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Maintainer,
) -> Machine:
    """Change machine state, opening or closing the matching downtime event.

    This is the single hook the floor uses, so availability data cannot drift out
    of step with what the machine board shows.
    """
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found")

    now = datetime.now()
    stopped_states = {MachineStatus.DOWN, MachineStatus.MAINTENANCE}
    open_event = db.scalar(
        select(DowntimeEvent)
        .where(DowntimeEvent.machine_id == machine.id, DowntimeEvent.ended_at.is_(None))
        .order_by(DowntimeEvent.started_at.desc())
    )

    if payload.status in stopped_states and open_event is None:
        if payload.reason_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A downtime reason is required to stop a machine")
        if db.get(DowntimeReason, payload.reason_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Downtime reason not found")
        db.add(
            DowntimeEvent(
                machine_id=machine.id,
                reason_id=payload.reason_id,
                started_at=now,
                reported_by_id=user.id,
                note=payload.note,
            )
        )
    elif payload.status not in stopped_states and open_event is not None:
        open_event.ended_at = now
        open_event.duration_minutes = round((now - open_event.started_at).total_seconds() / 60.0, 2)

    machine.status = payload.status
    machine.status_since = now
    db.commit()
    db.refresh(machine)
    return machine


# --- Downtime ---------------------------------------------------------------
@router.get("/downtime-reasons", response_model=list[DowntimeReasonRead])
def list_reasons(db: Session = Depends(get_db), _: User = AnyUser) -> list[DowntimeReason]:
    return list(db.scalars(select(DowntimeReason).order_by(DowntimeReason.code)))


@router.post("/downtime-reasons", response_model=DowntimeReasonRead, status_code=status.HTTP_201_CREATED)
def create_reason(
    payload: DowntimeReasonCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.PLANNER))
) -> DowntimeReason:
    if db.scalar(select(DowntimeReason).where(DowntimeReason.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Reason {payload.code} already exists")
    reason = DowntimeReason(**payload.model_dump())
    db.add(reason)
    db.commit()
    db.refresh(reason)
    return reason


@router.get("/downtime", response_model=list[DowntimeEventRead])
def list_downtime(
    machine_id: int | None = None,
    open_only: bool = False,
    days: int = 7,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[DowntimeEvent]:
    start, _end = _window(days, None)
    stmt = (
        select(DowntimeEvent)
        .options(
            selectinload(DowntimeEvent.machine).selectinload(Machine.work_center),
            selectinload(DowntimeEvent.reason),
        )
        .where(DowntimeEvent.started_at >= start)
    )
    if machine_id:
        stmt = stmt.where(DowntimeEvent.machine_id == machine_id)
    if open_only:
        stmt = stmt.where(DowntimeEvent.ended_at.is_(None))
    return list(db.scalars(stmt.order_by(DowntimeEvent.started_at.desc()).limit(limit)))


@router.post("/downtime", response_model=DowntimeEventRead, status_code=status.HTTP_201_CREATED)
def start_downtime(
    payload: DowntimeStart, db: Session = Depends(get_db), user: User = Maintainer
) -> DowntimeEvent:
    machine = db.get(Machine, payload.machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found")
    if db.get(DowntimeReason, payload.reason_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Downtime reason not found")
    if db.scalar(
        select(DowntimeEvent).where(
            DowntimeEvent.machine_id == machine.id, DowntimeEvent.ended_at.is_(None)
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{machine.code} already has an open downtime event")

    event = DowntimeEvent(
        machine_id=machine.id,
        reason_id=payload.reason_id,
        started_at=payload.started_at or datetime.now(),
        reported_by_id=user.id,
        note=payload.note,
    )
    db.add(event)
    machine.status = MachineStatus.DOWN
    machine.status_since = event.started_at
    db.commit()
    db.refresh(event)
    return event


@router.post("/downtime/{event_id}/end", response_model=DowntimeEventRead)
def end_downtime(
    event_id: int, payload: DowntimeEnd, db: Session = Depends(get_db), _: User = Maintainer
) -> DowntimeEvent:
    event = db.get(DowntimeEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Downtime event not found")
    if event.ended_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This event is already closed")

    ended_at = payload.ended_at or datetime.now()
    if ended_at < event.started_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "End time is before the start time")

    event.ended_at = ended_at
    event.duration_minutes = round((ended_at - event.started_at).total_seconds() / 60.0, 2)
    if payload.note:
        event.note = payload.note

    machine = db.get(Machine, event.machine_id)
    machine.status = MachineStatus.IDLE
    machine.status_since = ended_at

    db.commit()
    db.refresh(event)
    return event


# --- Maintenance ------------------------------------------------------------
@router.get("/maintenance", response_model=list[MaintenanceRequestRead])
def list_maintenance(
    open_only: bool = True, db: Session = Depends(get_db), _: User = AnyUser
) -> list[MaintenanceRequest]:
    stmt = select(MaintenanceRequest).options(
        selectinload(MaintenanceRequest.machine).selectinload(Machine.work_center)
    )
    if open_only:
        stmt = stmt.where(MaintenanceRequest.status != "CLOSED")
    return list(db.scalars(stmt.order_by(MaintenanceRequest.id.desc())))


@router.post("/maintenance", response_model=MaintenanceRequestRead, status_code=status.HTTP_201_CREATED)
def create_maintenance(
    payload: MaintenanceRequestCreate, db: Session = Depends(get_db), user: User = Maintainer
) -> MaintenanceRequest:
    if db.get(Machine, payload.machine_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found")
    request = MaintenanceRequest(
        request_no=next_number(db, "MNT"), requested_by_id=user.id, **payload.model_dump()
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


@router.post("/maintenance/{request_id}/close", response_model=MaintenanceRequestRead)
def close_maintenance(
    request_id: int, db: Session = Depends(get_db), _: User = Maintainer
) -> MaintenanceRequest:
    request = db.get(MaintenanceRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance request not found")
    request.status = "CLOSED"
    request.closed_at = datetime.now()
    db.commit()
    db.refresh(request)
    return request


# --- OEE --------------------------------------------------------------------
@router.get("/oee", response_model=list[OeeRead])
def oee(
    days: int = 1,
    hours: int | None = None,
    machine_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[dict]:
    start, end = _window(days, hours)
    if machine_id:
        machine = db.get(Machine, machine_id)
        if machine is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found")
        return [oee_service.calculate_oee(db, machine, start, end).as_dict()]
    return [result.as_dict() for result in oee_service.plant_oee(db, start, end)]


@router.get("/downtime-pareto")
def downtime_pareto(
    days: int = 7,
    include_planned: bool = False,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[dict]:
    start, end = _window(days, None)
    return oee_service.downtime_pareto(db, start, end, include_planned=include_planned)
