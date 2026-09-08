"""Production calendar.

One feed of everything that happened or is going to happen, so a planner can see
the month rather than a list. Three kinds of event, deliberately distinct:

  ACTUAL   what the floor really booked - history, not editable
  PLANNED  the current plan for an open order - the planner's to move
  DUE      the promise to the customer - moved only with a reason

Keeping them apart is the point. A calendar that draws the plan and the promise
as the same object is how a plant talks itself into believing it is on time.
"""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...enums import OrderStatus, Role
from ...database import get_db
from ...models.production import Confirmation, OrderOperation, ProductionOrder
from ...models.user import User
from ...schemas.common import to_local_naive
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/calendar", tags=["calendar"])

AnyUser = Depends(get_current_user)
Planner = Depends(require_roles(Role.PLANNER))

OPEN_STATUSES = [OrderStatus.DRAFT, OrderStatus.RELEASED, OrderStatus.IN_PROGRESS]


class CalendarEvent(BaseModel):
    id: str
    kind: str                     # ACTUAL | PLANNED | DUE
    date: date                    # the day it belongs on
    end_date: date | None = None  # for spans
    # The real instants behind those dates. Without them an editor can only
    # guess the time of day, and saving would quietly rewrite the plan.
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    order_id: int
    order_no: str
    item_code: str
    item_name: str
    title: str
    detail: str | None = None
    status: str
    qty: float = 0.0
    editable: bool = False


class CalendarFeed(BaseModel):
    start: date
    end: date
    events: list[CalendarEvent]


class RescheduleRequest(BaseModel):
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    due_date: datetime | None = None
    # Moving the customer promise is a different act from moving the plan, so it
    # has to be asked for explicitly rather than slipping through in a payload.
    move_due_date: bool = False
    reason: str | None = None

    _local_times = field_validator("planned_start", "planned_end", "due_date")(to_local_naive)


@router.get("", response_model=CalendarFeed)
def calendar(
    start: date = Query(..., description="First day shown"),
    end: date = Query(..., description="Last day shown, inclusive"),
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> CalendarFeed:
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "End date is before the start date")
    if (end - start).days > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Range is limited to 200 days")

    frm = datetime.combine(start, time())
    to = datetime.combine(end, time.max)
    events: list[CalendarEvent] = []

    # --- what actually happened ---
    rows = db.execute(
        select(Confirmation, OrderOperation, ProductionOrder)
        .join(OrderOperation, Confirmation.operation_id == OrderOperation.id)
        .join(ProductionOrder, OrderOperation.order_id == ProductionOrder.id)
        .options(selectinload(ProductionOrder.item))
        .where(Confirmation.ended_at >= frm, Confirmation.ended_at <= to)
        .order_by(Confirmation.ended_at)
    ).all()
    for confirmation, operation, order in rows:
        scrap = f" · {confirmation.qty_scrap:g} scrap" if confirmation.qty_scrap else ""
        events.append(
            CalendarEvent(
                id=f"c{confirmation.id}",
                kind="ACTUAL",
                date=confirmation.ended_at.date(),
                order_id=order.id,
                order_no=order.order_no,
                item_code=order.item.code,
                item_name=order.item.name,
                ends_at=confirmation.ended_at,
                title=f"OP {operation.seq} {operation.name}",
                detail=f"{confirmation.qty_good:g} good{scrap}",
                status=str(order.status),
                qty=confirmation.qty_good,
                editable=False,
            )
        )

    # --- what is planned ---
    open_orders = db.scalars(
        select(ProductionOrder)
        .options(selectinload(ProductionOrder.item))
        .where(ProductionOrder.status.in_(OPEN_STATUSES))
    )
    for order in open_orders:
        if order.planned_start and order.planned_end:
            if order.planned_start.date() <= end and order.planned_end.date() >= start:
                events.append(
                    CalendarEvent(
                        id=f"p{order.id}",
                        kind="PLANNED",
                        date=order.planned_start.date(),
                        end_date=order.planned_end.date(),
                        starts_at=order.planned_start,
                        ends_at=order.planned_end,
                        order_id=order.id,
                        order_no=order.order_no,
                        item_code=order.item.code,
                        item_name=order.item.name,
                        title=f"{order.order_no} · {order.item.code}",
                        detail=f"{order.qty_ordered:g} {order.item.uom} · priority {order.priority}",
                        status=str(order.status),
                        qty=order.qty_ordered,
                        editable=True,
                    )
                )
        if order.due_date and start <= order.due_date.date() <= end:
            events.append(
                CalendarEvent(
                    id=f"d{order.id}",
                    kind="DUE",
                    date=order.due_date.date(),
                    starts_at=order.due_date,
                    order_id=order.id,
                    order_no=order.order_no,
                    item_code=order.item.code,
                    item_name=order.item.name,
                    title=f"Due · {order.order_no}",
                    detail=f"{order.qty_ordered:g} {order.item.uom} promised",
                    status=str(order.status),
                    qty=order.qty_ordered,
                    editable=True,
                )
            )

    return CalendarFeed(start=start, end=end, events=events)


@router.patch("/orders/{order_id}", response_model=CalendarEvent)
def reschedule(
    order_id: int,
    payload: RescheduleRequest,
    db: Session = Depends(get_db),
    _: User = Planner,
) -> CalendarEvent:
    """Move one order's plan, and only its plan unless told otherwise."""
    order = db.get(ProductionOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production order not found")
    if order.status not in OPEN_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{order.order_no} is {order.status} - finished work cannot be re-planned.",
        )

    if payload.planned_start is not None:
        order.planned_start = payload.planned_start
    if payload.planned_end is not None:
        order.planned_end = payload.planned_end
    if order.planned_start and order.planned_end and order.planned_end < order.planned_start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The plan would finish before it starts.")

    if payload.move_due_date:
        if payload.due_date is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No new due date was given.")
        if not payload.reason:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Moving a customer due date needs a reason - it is a re-promise, not a re-plan.",
            )
        order.due_date = payload.due_date
        stamp = datetime.now().strftime("%Y-%m-%d")
        note = f"[{stamp}] Due date moved: {payload.reason}"
        order.note = f"{order.note}\n{note}" if order.note else note

    db.commit()
    db.refresh(order)

    return CalendarEvent(
        id=f"p{order.id}",
        kind="PLANNED",
        date=(order.planned_start or datetime.now()).date(),
        end_date=(order.planned_end or order.planned_start or datetime.now()).date(),
        starts_at=order.planned_start,
        ends_at=order.planned_end,
        order_id=order.id,
        order_no=order.order_no,
        item_code=order.item.code,
        item_name=order.item.name,
        title=f"{order.order_no} · {order.item.code}",
        detail=f"{order.qty_ordered:g} {order.item.uom} · priority {order.priority}",
        status=str(order.status),
        qty=order.qty_ordered,
        editable=True,
    )
