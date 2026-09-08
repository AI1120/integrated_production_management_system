"""Process, time and cost optimisation."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...enums import Role
from ...models.production import ProductionOrder
from ...models.user import User
from ...schemas.optimization import (
    ApplyScheduleRequest,
    ComparisonRead,
    CostSummaryRead,
    OptimizationReport,
    OrderCostRead,
    ScheduleRead,
)
from ...services import costing_service as costing
from ...services import optimization_service as optimize
from ...services import scheduling_service as sched
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/optimization", tags=["optimization"])

AnyUser = Depends(get_current_user)
Planner = Depends(require_roles(Role.PLANNER))


@router.get("/rules")
def list_rules(_: User = AnyUser) -> dict:
    """The dispatch rules and objectives the planner can choose between."""
    return {
        "rules": [{"key": k, "description": v} for k, v in sched.DISPATCH_RULES.items()],
        "objectives": [{"key": k, "description": v} for k, v in sched.OBJECTIVES.items()],
    }


@router.get("/schedule", response_model=ScheduleRead)
def schedule(
    rule: str = "PRIORITY",
    horizon_days: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> dict:
    try:
        built = sched.build_schedule(db, rule=rule, horizon_days=horizon_days)
    except sched.SchedulingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return _schedule_dict(built)


@router.get("/compare", response_model=ComparisonRead)
def compare(
    horizon_days: int = Query(default=30, ge=1, le=180),
    objective: str = "total_lateness_hours",
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> dict:
    try:
        return sched.compare_rules(db, horizon_days=horizon_days, objective=objective)
    except sched.SchedulingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/cost", response_model=CostSummaryRead)
def cost(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), _: User = AnyUser) -> dict:
    return costing.cost_summary(db, days=days)


@router.get("/cost/orders", response_model=list[OrderCostRead])
def cost_by_order(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[dict]:
    return [c.as_dict() for c in costing.cost_orders(db, days=days, limit=limit)]


@router.get("", response_model=OptimizationReport)
def report(
    rule: str = "PRIORITY",
    horizon_days: int = Query(default=30, ge=1, le=180),
    objective: str = "total_lateness_hours",
    cost_days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> dict:
    try:
        result = optimize.full_report(
            db, rule=rule, horizon_days=horizon_days, objective=objective, cost_days=cost_days
        )
    except sched.SchedulingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    result["schedule"] = _schedule_dict(result["schedule"])
    return result


@router.post("/apply", response_model=ScheduleRead)
def apply_schedule(
    payload: ApplyScheduleRequest,
    db: Session = Depends(get_db),
    _: User = Planner,
) -> dict:
    """Write the computed schedule back onto the orders as planned dates.

    Explicitly opt-in: everything else here is analysis, but this changes the
    order book, so it is a planner action rather than a side effect of looking
    at the page.
    """
    try:
        built = sched.build_schedule(db, rule=payload.rule, horizon_days=payload.horizon_days)
    except sched.SchedulingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    for scheduled in built.orders:
        order = db.get(ProductionOrder, scheduled.order_id)
        if order is None:
            continue
        # due_date is deliberately untouched: it is the promise to the customer,
        # and rewriting it would make every schedule look perfectly on time.
        order.planned_start = scheduled.start
        order.planned_end = scheduled.end
    db.commit()
    return _schedule_dict(built)


def _schedule_dict(built: sched.Schedule) -> dict:
    """Flatten the dataclass graph for the response model."""
    def op(o: sched.ScheduledOperation) -> dict:
        return {
            "order_id": o.order_id, "order_no": o.order_no, "item_code": o.item_code,
            "operation_id": o.operation_id, "seq": o.seq, "name": o.name,
            "work_center_id": o.work_center_id, "work_center_code": o.work_center_code,
            "machine_id": o.machine_id, "machine_code": o.machine_code,
            "qty": o.qty, "setup_minutes": o.setup_minutes, "run_minutes": o.run_minutes,
            "start": o.start, "end": o.end,
            "offset_minutes": o.offset_minutes, "work_minutes": o.work_minutes,
        }

    return {
        "rule": built.rule,
        "horizon_start": built.horizon_start,
        "horizon_end": built.horizon_end,
        "orders": [
            {
                "order_id": o.order_id, "order_no": o.order_no, "item_code": o.item_code,
                "item_name": o.item_name, "qty": o.qty, "priority": o.priority, "due": o.due,
                "start": o.start, "end": o.end, "lateness_hours": o.lateness_hours,
                "operations": [op(x) for x in o.operations],
            }
            for o in built.orders
        ],
        "operations": [op(o) for o in built.operations],
        "unscheduled": built.unscheduled,
        "day_marks": built.day_marks,
        "makespan_hours": built.makespan_hours,
        "total_lateness_hours": built.total_lateness_hours,
        "max_lateness_hours": built.max_lateness_hours,
        "late_orders": built.late_orders,
        "utilisation": built.utilisation,
    }
