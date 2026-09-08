"""Finite-capacity forward scheduler.

Takes the open order book and loads it onto real machines, respecting three
constraints the planner otherwise holds in their head:

  1. Routing sequence - operation 30 cannot start before 20 has finished.
  2. Machine capacity - a machine runs one job at a time.
  3. The shift calendar - work only happens when the plant is open.

This is a *heuristic* scheduler, not an optimiser. It builds one feasible
schedule per dispatch rule and reports what each costs; searching for the
provably shortest schedule is NP-hard and would not survive contact with a
shop floor that reschedules twice a shift anyway. What it does give you is a
defensible answer to "when will this order actually finish, and which machine
is the reason?"
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..enums import OperationStatus, OrderStatus
from ..models.equipment import Machine
from ..models.master import WorkCenter
from ..models.production import OrderOperation, ProductionOrder
from . import calendar_service as cal


class SchedulingError(Exception):
    """Raised when a schedule cannot be built at all."""


# --- dispatch rules ---------------------------------------------------------
DISPATCH_RULES: dict[str, str] = {
    "PRIORITY": "Planner priority, then due date",
    "EDD": "Earliest due date first",
    "SPT": "Shortest processing time first",
    "LPT": "Longest processing time first",
    "CR": "Critical ratio - least slack per hour of work first",
}

# Objectives a schedule can be judged against. Lower is better for all of them.
OBJECTIVES: dict[str, str] = {
    "total_lateness_hours": "Total lateness across all orders",
    "late_orders": "Number of orders finishing after their due date",
    "makespan_hours": "Time to clear the whole order book",
    "max_lateness_hours": "Worst single late order",
}


@dataclass
class ScheduledOperation:
    order_id: int
    order_no: str
    item_code: str
    operation_id: int
    seq: int
    name: str
    work_center_id: int
    work_center_code: str
    machine_id: int
    machine_code: str
    qty: float
    setup_minutes: float
    run_minutes: float
    start: datetime
    end: datetime
    # Position on a working-time axis: productive minutes elapsed since the
    # horizon began, so nights and weekends take up no width.
    offset_minutes: float = 0.0
    work_minutes: float = 0.0

    @property
    def minutes(self) -> float:
        return self.setup_minutes + self.run_minutes


@dataclass
class ScheduledOrder:
    order_id: int
    order_no: str
    item_code: str
    item_name: str
    qty: float
    priority: int
    due: datetime | None
    start: datetime
    end: datetime
    lateness_hours: float          # positive = late; 0 when on time or no due date
    operations: list[ScheduledOperation] = field(default_factory=list)


@dataclass
class Schedule:
    rule: str
    horizon_start: datetime
    horizon_end: datetime
    orders: list[ScheduledOrder]
    operations: list[ScheduledOperation]
    unscheduled: list[dict]
    day_marks: list[dict]
    makespan_hours: float
    total_lateness_hours: float
    max_lateness_hours: float
    late_orders: int
    utilisation: list[dict]

    def metric(self, objective: str) -> float:
        return float(getattr(self, objective))


# --- the scheduler ----------------------------------------------------------
def _remaining_qty(order: ProductionOrder, operation: OrderOperation) -> float:
    """Units this operation still has to process."""
    return max(order.qty_ordered - operation.qty_completed - operation.qty_scrapped, 0.0)


def _operation_minutes(order: ProductionOrder, operation: OrderOperation) -> float:
    qty = _remaining_qty(order, operation)
    if qty <= 0:
        return 0.0
    # Setup is paid once per operation regardless of how many units remain.
    return operation.setup_minutes + qty * operation.run_minutes_per_unit


def _order_work_minutes(order: ProductionOrder) -> float:
    return sum(
        _operation_minutes(order, op)
        for op in order.operations
        if op.status is not OperationStatus.COMPLETED
    )


def _sort_orders(orders: list[ProductionOrder], rule: str, now: datetime) -> list[ProductionOrder]:
    far_future = now + timedelta(days=3650)

    def due(order: ProductionOrder) -> datetime:
        return order.due_date or order.planned_end or far_future

    if rule == "EDD":
        return sorted(orders, key=lambda o: (due(o), o.priority, o.id))
    if rule == "SPT":
        return sorted(orders, key=lambda o: (_order_work_minutes(o), o.id))
    if rule == "LPT":
        return sorted(orders, key=lambda o: (-_order_work_minutes(o), o.id))
    if rule == "CR":
        def critical_ratio(order: ProductionOrder) -> float:
            work = _order_work_minutes(order) or 1.0
            slack = (due(order) - now).total_seconds() / 60.0
            return slack / work
        return sorted(orders, key=lambda o: (critical_ratio(o), o.id))
    # PRIORITY (default): the planner's own number wins, due date breaks ties.
    return sorted(orders, key=lambda o: (o.priority, due(o), o.id))


def open_orders(db: Session) -> list[ProductionOrder]:
    """Everything still to be made: drafted, released or part-built."""
    return list(
        db.scalars(
            select(ProductionOrder)
            .options(
                selectinload(ProductionOrder.operations).selectinload(OrderOperation.work_center),
                selectinload(ProductionOrder.item),
            )
            .where(
                ProductionOrder.status.in_(
                    [OrderStatus.DRAFT, OrderStatus.RELEASED, OrderStatus.IN_PROGRESS]
                )
            )
        )
    )


def build_schedule(
    db: Session,
    *,
    rule: str = "PRIORITY",
    horizon_start: datetime | None = None,
    horizon_days: int = 30,
) -> Schedule:
    if rule not in DISPATCH_RULES:
        raise SchedulingError(f"Unknown dispatch rule {rule!r}.")

    now = horizon_start or datetime.now()
    horizon_end = now + timedelta(days=horizon_days)
    windows = cal.shift_windows(db, now, horizon_end)
    if not windows:
        raise SchedulingError("No production time in the horizon - check the shift calendar.")

    machines = list(db.scalars(select(Machine).where(Machine.is_active.is_(True))))
    by_work_center: dict[int, list[Machine]] = {}
    for machine in machines:
        by_work_center.setdefault(machine.work_center_id, []).append(machine)

    work_centers = {wc.id: wc for wc in db.scalars(select(WorkCenter))}
    orders = _sort_orders(open_orders(db), rule, now)

    # Every machine is free from the start of the horizon.
    machine_free: dict[int, datetime] = {m.id: now for m in machines}

    scheduled_ops: list[ScheduledOperation] = []
    scheduled_orders: list[ScheduledOrder] = []
    unscheduled: list[dict] = []

    for order in orders:
        pending = [op for op in sorted(order.operations, key=lambda o: o.seq)
                   if op.status is not OperationStatus.COMPLETED]
        if not pending:
            continue

        # Everything is loaded as early as capacity allows, from now.
        #
        # planned_start is deliberately NOT used as an earliest-start constraint:
        # it is this scheduler's own output, so feeding it back in ratchets each
        # run against the last one and re-planning slowly gets worse. The date
        # that constrains the answer is the due date, not a previous plan.
        previous_end = now
        placed: list[ScheduledOperation] = []
        failed: str | None = None

        for operation in pending:
            candidates = by_work_center.get(operation.work_center_id, [])
            if not candidates:
                failed = f"no active machine at {operation.work_center.code}"
                break

            minutes = _operation_minutes(order, operation)
            qty = _remaining_qty(order, operation)

            # Pick the machine that finishes this operation soonest - not the one
            # that starts it soonest. A machine free now but slow to reach the
            # next shift can finish later than one free in an hour.
            best: tuple[Machine, datetime, datetime] | None = None
            for machine in candidates:
                earliest = max(previous_end, machine_free[machine.id])
                slot = cal.place_work(windows, earliest, minutes)
                if slot is None:
                    continue
                if best is None or slot[1] < best[2]:
                    best = (machine, slot[0], slot[1])

            if best is None:
                failed = f"does not fit within {horizon_days} days"
                break

            machine, start, end = best
            machine_free[machine.id] = end
            previous_end = end
            placed.append(
                ScheduledOperation(
                    order_id=order.id,
                    order_no=order.order_no,
                    item_code=order.item.code,
                    operation_id=operation.id,
                    seq=operation.seq,
                    name=operation.name,
                    work_center_id=operation.work_center_id,
                    work_center_code=operation.work_center.code,
                    machine_id=machine.id,
                    machine_code=machine.code,
                    qty=qty,
                    setup_minutes=operation.setup_minutes,
                    run_minutes=max(minutes - operation.setup_minutes, 0.0),
                    start=start,
                    end=end,
                )
            )

        if failed:
            # Roll back this order's placements so a schedule is never half-true.
            for op in placed:
                machine_free[op.machine_id] = min(machine_free[op.machine_id], op.start)
            unscheduled.append(
                {"order_id": order.id, "order_no": order.order_no,
                 "item_code": order.item.code, "reason": failed}
            )
            continue

        scheduled_ops.extend(placed)
        order_start = min(op.start for op in placed)
        order_end = max(op.end for op in placed)
        commitment = order.due_date or order.planned_end
        lateness = 0.0
        if commitment and order_end > commitment:
            lateness = (order_end - commitment).total_seconds() / 3600.0

        scheduled_orders.append(
            ScheduledOrder(
                order_id=order.id,
                order_no=order.order_no,
                item_code=order.item.code,
                item_name=order.item.name,
                qty=order.qty_ordered,
                priority=order.priority,
                due=commitment,
                start=order_start,
                end=order_end,
                lateness_hours=round(lateness, 2),
                operations=placed,
            )
        )

    # --- working-time axis ---
    for op in scheduled_ops:
        op.offset_minutes = round(cal.working_minutes_between(windows, now, op.start), 2)
        op.work_minutes = round(cal.working_minutes_between(windows, op.start, op.end), 2)

    # --- metrics ---
    if scheduled_ops:
        finish = max(op.end for op in scheduled_ops)
        makespan = cal.working_minutes_between(windows, now, finish) / 60.0
    else:
        makespan = 0.0

    # One tick per shift, labelled with its date - the only gridline that means
    # anything once the idle hours are squeezed out.
    day_marks = []
    seen_days: set = set()
    for window_start, _window_end in windows:
        if window_start > (max((op.end for op in scheduled_ops), default=now)):
            break
        key = window_start.date()
        if key in seen_days:
            continue
        seen_days.add(key)
        day_marks.append({
            "label": window_start.strftime("%a %d %b"),
            "offset_minutes": round(cal.working_minutes_between(windows, now, window_start), 2),
        })

    lateness_values = [o.lateness_hours for o in scheduled_orders]
    utilisation = _utilisation(db, scheduled_ops, work_centers, by_work_center, windows, now, horizon_end)

    return Schedule(
        rule=rule,
        horizon_start=now,
        horizon_end=horizon_end,
        orders=scheduled_orders,
        operations=scheduled_ops,
        unscheduled=unscheduled,
        day_marks=day_marks,
        makespan_hours=round(makespan, 2),
        total_lateness_hours=round(sum(lateness_values), 2),
        max_lateness_hours=round(max(lateness_values, default=0.0), 2),
        late_orders=sum(1 for value in lateness_values if value > 0),
        utilisation=utilisation,
    )


def _utilisation(
    db: Session,
    operations: list[ScheduledOperation],
    work_centers: dict[int, WorkCenter],
    by_work_center: dict[int, list[Machine]],
    windows: list[cal.Window],
    frm: datetime,
    to: datetime,
) -> list[dict]:
    """Loaded hours against available hours, per work centre.

    Available time is bounded by the *loaded* span rather than the whole
    horizon: measuring a two-day order book against a thirty-day horizon would
    report every work centre at 6% and hide the bottleneck completely.
    """
    if operations:
        span_end = max(op.end for op in operations)
    else:
        span_end = frm
    span_minutes = cal.working_minutes_between(windows, frm, span_end)

    loaded: dict[int, float] = {}
    setup_load: dict[int, float] = {}
    for op in operations:
        loaded[op.work_center_id] = loaded.get(op.work_center_id, 0.0) + op.minutes
        setup_load[op.work_center_id] = setup_load.get(op.work_center_id, 0.0) + op.setup_minutes

    rows: list[dict] = []
    for wc_id, wc in sorted(work_centers.items(), key=lambda kv: kv[1].code):
        machine_count = len(by_work_center.get(wc_id, []))
        capacity = span_minutes * machine_count
        load = loaded.get(wc_id, 0.0)
        rows.append(
            {
                "work_center_id": wc_id,
                "work_center_code": wc.code,
                "work_center_name": wc.name,
                "machines": machine_count,
                "loaded_hours": round(load / 60.0, 2),
                "capacity_hours": round(capacity / 60.0, 2),
                "setup_hours": round(setup_load.get(wc_id, 0.0) / 60.0, 2),
                "utilisation": round(load / capacity, 4) if capacity > 0 else 0.0,
            }
        )
    rows.sort(key=lambda r: r["utilisation"], reverse=True)
    return rows


def compare_rules(
    db: Session,
    *,
    horizon_start: datetime | None = None,
    horizon_days: int = 30,
    objective: str = "total_lateness_hours",
) -> dict:
    """Build the order book under every dispatch rule and report what each costs.

    This is the optimisation: the search space is the choice of rule, and the
    objective is stated rather than assumed, because a plant chasing due dates
    and a plant chasing throughput want different answers.
    """
    if objective not in OBJECTIVES:
        raise SchedulingError(f"Unknown objective {objective!r}.")

    now = horizon_start or datetime.now()
    results = []
    for rule in DISPATCH_RULES:
        schedule = build_schedule(db, rule=rule, horizon_start=now, horizon_days=horizon_days)
        results.append(
            {
                "rule": rule,
                "description": DISPATCH_RULES[rule],
                "makespan_hours": schedule.makespan_hours,
                "total_lateness_hours": schedule.total_lateness_hours,
                "max_lateness_hours": schedule.max_lateness_hours,
                "late_orders": schedule.late_orders,
                "scheduled_orders": len(schedule.orders),
                "unscheduled_orders": len(schedule.unscheduled),
            }
        )

    ranked = sorted(results, key=lambda r: (r[objective], r["makespan_hours"]))
    best = ranked[0]
    baseline = next(r for r in results if r["rule"] == "PRIORITY")
    improvement = round(baseline[objective] - best[objective], 2)

    return {
        "objective": objective,
        "objective_label": OBJECTIVES[objective],
        "results": results,
        "best_rule": best["rule"],
        "baseline_rule": "PRIORITY",
        "improvement": improvement,
        "improvement_pct": round(improvement / baseline[objective] * 100, 1)
        if baseline[objective]
        else 0.0,
    }
