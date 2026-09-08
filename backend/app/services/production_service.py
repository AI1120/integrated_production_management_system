"""Work-order lifecycle: create -> release -> confirm -> complete.

The order takes a *copy* of the BOM and routing at creation time. Later master
data edits therefore never rewrite what the floor was told to build - which is
what makes the production history auditable.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import ItemType, LocationType, LotStatus, MovementType, OperationStatus, OrderStatus
from ..models.master import Bom, Item, Routing
from ..models.production import Confirmation, OrderMaterial, OrderOperation, ProductionOrder
from . import inventory_service as inv
from .numbering import next_number


class ProductionError(Exception):
    """Raised when an operation is not allowed in the order's current state."""


def _active_bom(db: Session, item_id: int) -> Bom | None:
    return db.scalar(
        select(Bom).where(Bom.item_id == item_id, Bom.is_active.is_(True)).order_by(Bom.id.desc()).limit(1)
    )


def _active_routing(db: Session, item_id: int) -> Routing | None:
    return db.scalar(
        select(Routing)
        .where(Routing.item_id == item_id, Routing.is_active.is_(True))
        .order_by(Routing.id.desc())
        .limit(1)
    )


def create_order(
    db: Session,
    *,
    item_id: int,
    qty: float,
    bom_id: int | None = None,
    routing_id: int | None = None,
    planned_start: datetime | None = None,
    planned_end: datetime | None = None,
    due_date: datetime | None = None,
    priority: int = 5,
    customer_id: int | None = None,
    sales_ref: str | None = None,
    note: str | None = None,
) -> ProductionOrder:
    if qty <= 0:
        raise ProductionError("Order quantity must be greater than zero.")

    item = db.get(Item, item_id)
    if item is None:
        raise ProductionError(f"Unknown item id {item_id}.")
    if item.item_type not in (ItemType.FINISHED_GOOD, ItemType.SUB_ASSEMBLY):
        raise ProductionError(f"{item.code} is a {item.item_type} and cannot be produced.")

    bom = db.get(Bom, bom_id) if bom_id else _active_bom(db, item_id)
    routing = db.get(Routing, routing_id) if routing_id else _active_routing(db, item_id)
    if routing is None:
        raise ProductionError(f"{item.code} has no active routing - cannot schedule work.")

    order = ProductionOrder(
        order_no=next_number(db, "WO"),
        item_id=item_id,
        bom_id=bom.id if bom else None,
        routing_id=routing.id,
        qty_ordered=qty,
        status=OrderStatus.DRAFT,
        priority=priority,
        planned_start=planned_start,
        planned_end=planned_end,
        due_date=due_date or planned_end,
        customer_id=customer_id,
        sales_ref=sales_ref,
        note=note,
    )
    db.add(order)
    db.flush()

    # Freeze the routing onto the order.
    for step in routing.operations:
        db.add(
            OrderOperation(
                order_id=order.id,
                seq=step.seq,
                name=step.name,
                work_center_id=step.work_center_id,
                setup_minutes=step.setup_minutes,
                run_minutes_per_unit=step.run_minutes_per_unit,
                requires_inspection=step.requires_inspection,
                instructions=step.instructions,
                status=OperationStatus.PENDING,
            )
        )

    # Explode the BOM, inflating each line by its expected scrap.
    if bom:
        for line in bom.lines:
            required = qty * line.qty_per * (1.0 + line.scrap_pct / 100.0)
            db.add(
                OrderMaterial(
                    order_id=order.id,
                    line_no=line.line_no,
                    component_id=line.component_id,
                    operation_seq=line.operation_seq,
                    qty_required=round(required, 4),
                )
            )

    db.flush()
    db.refresh(order)
    return order


def release_order(db: Session, order: ProductionOrder) -> ProductionOrder:
    if order.status is not OrderStatus.DRAFT:
        raise ProductionError(f"Order {order.order_no} is {order.status} and cannot be released.")
    order.status = OrderStatus.RELEASED
    order.output_lot_no = order.output_lot_no or order.order_no.replace("WO-", "LOT-")
    db.flush()
    return order


def issue_material(
    db: Session,
    *,
    order: ProductionOrder,
    material: OrderMaterial,
    qty: float,
    lot_no: str | None = None,
    from_location_id: int | None = None,
    user_id: int | None = None,
) -> list[dict]:
    """Issue components to the order, picking FIFO when no lot is named."""
    if order.status not in (OrderStatus.RELEASED, OrderStatus.IN_PROGRESS):
        raise ProductionError(f"Order {order.order_no} must be released before material can be issued.")
    if qty <= 0:
        raise ProductionError("Issue quantity must be greater than zero.")

    wip = inv.default_location(db, LocationType.WIP)
    issued: list[dict] = []

    if lot_no:
        source = from_location_id
        if source is None:
            lot = db.scalar(
                select(inv.StockLot).where(
                    inv.StockLot.item_id == material.component_id,
                    inv.StockLot.lot_no == lot_no,
                    inv.StockLot.qty > 0,
                )
            )
            if lot is None:
                raise inv.StockError(f"Lot {lot_no} not found in stock.")
            source = lot.location_id
        picks = [(lot_no, source, qty)]
    else:
        picks = [
            (lot.lot_no, lot.location_id, take)
            for lot, take in inv.allocate_fifo(
                db, item_id=material.component_id, qty=qty, location_id=from_location_id
            )
        ]

    for pick_lot, pick_location, pick_qty in picks:
        inv.post_movement(
            db,
            movement_type=MovementType.ISSUE,
            item_id=material.component_id,
            qty=pick_qty,
            lot_no=pick_lot,
            from_location_id=pick_location,
            to_location_id=wip.id,
            ref_type="PRODUCTION_ORDER",
            ref_id=order.id,
            ref_no=order.order_no,
            user_id=user_id,
            note=f"Issue to {order.order_no} line {material.line_no}",
        )
        issued.append({"lot_no": pick_lot, "qty": pick_qty, "from_location_id": pick_location})

    material.qty_issued += qty
    db.flush()
    return issued


def _operation_target(order: ProductionOrder, operation: OrderOperation) -> float:
    """How many units this step can ever process.

    The first step is capped by the order quantity; every later step is capped by
    what actually cleared the step before it. Without this, units scrapped early
    would make the downstream steps impossible to complete.
    """
    previous = [op for op in order.operations if op.seq < operation.seq]
    if not previous:
        return order.qty_ordered
    return min(op.qty_completed for op in previous)


def _recompute_operation_statuses(order: ProductionOrder, at: datetime) -> None:
    """Re-derive every operation's status after a booking anywhere on the order."""
    upstream = order.qty_ordered
    for operation in sorted(order.operations, key=lambda op: op.seq):
        if operation.status is OperationStatus.SKIPPED:
            continue
        booked = operation.qty_completed + operation.qty_scrapped
        if upstream > 0 and booked >= upstream - 1e-9:
            operation.status = OperationStatus.COMPLETED
            operation.actual_end = operation.actual_end or at
        elif booked > 0:
            operation.status = OperationStatus.RUNNING
            operation.actual_end = None
        else:
            operation.status = OperationStatus.PENDING
        upstream = operation.qty_completed


def confirm_operation(
    db: Session,
    *,
    operation: OrderOperation,
    qty_good: float,
    qty_scrap: float = 0.0,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    operator_id: int | None = None,
    defect_code_id: int | None = None,
    machine_id: int | None = None,
    note: str | None = None,
) -> Confirmation:
    """Book production against one operation and roll the totals up to the order."""
    order = operation.order
    if order.status in (OrderStatus.COMPLETED, OrderStatus.CLOSED, OrderStatus.CANCELLED):
        raise ProductionError(f"Order {order.order_no} is {order.status}.")
    if order.status is OrderStatus.DRAFT:
        raise ProductionError(f"Order {order.order_no} must be released before reporting production.")
    if qty_good < 0 or qty_scrap < 0:
        raise ProductionError("Quantities cannot be negative.")
    if qty_good + qty_scrap <= 0:
        raise ProductionError("Report at least one good or scrapped unit.")

    # One guard covers both over-reporting and running a step out of sequence.
    booked = operation.qty_completed + operation.qty_scrapped + qty_good + qty_scrap
    target = _operation_target(order, operation)
    if booked > target + 1e-9:
        if any(op.seq < operation.seq for op in order.operations):
            raise ProductionError(
                f"Only {target:g} units have cleared the previous operation, "
                f"so operation {operation.seq} cannot book {booked:g}."
            )
        raise ProductionError(
            f"Operation {operation.seq} would be over-reported: "
            f"{booked:g} booked against an order of {order.qty_ordered:g}."
        )

    now = datetime.now()
    ended_at = ended_at or now
    started_at = started_at or ended_at
    duration = max((ended_at - started_at).total_seconds() / 60.0, 0.0)

    confirmation = Confirmation(
        operation_id=operation.id,
        operator_id=operator_id,
        qty_good=qty_good,
        qty_scrap=qty_scrap,
        defect_code_id=defect_code_id,
        started_at=started_at,
        ended_at=ended_at,
        duration_minutes=duration,
        note=note,
    )
    db.add(confirmation)

    operation.qty_completed += qty_good
    operation.qty_scrapped += qty_scrap
    if machine_id:
        operation.machine_id = machine_id
    if operation.actual_start is None:
        operation.actual_start = started_at

    _recompute_operation_statuses(order, ended_at)

    if order.status is OrderStatus.RELEASED:
        order.status = OrderStatus.IN_PROGRESS
        order.actual_start = order.actual_start or started_at

    # Only the last routing step adds to finished quantity.
    last_operation = max(order.operations, key=lambda op: op.seq)
    if operation.id == last_operation.id:
        order.qty_produced += qty_good
        _receive_finished_goods(db, order=order, qty=qty_good, user_id=operator_id)
    order.qty_scrapped += qty_scrap

    if all(
        op.status in (OperationStatus.COMPLETED, OperationStatus.SKIPPED)
        for op in order.operations
    ):
        order.status = OrderStatus.COMPLETED
        order.actual_end = ended_at

    db.flush()
    db.refresh(confirmation)
    return confirmation


def _receive_finished_goods(db: Session, *, order: ProductionOrder, qty: float, user_id: int | None) -> None:
    """Book good output into stock, quarantined when the item needs final QC."""
    if qty <= 0:
        return

    needs_qc = any(op.requires_inspection for op in order.operations)
    location = (
        inv.default_location(db, LocationType.QUARANTINE)
        if needs_qc
        else inv.stock_location_for(db, order.item)
    )
    lot_no = order.output_lot_no or order.order_no.replace("WO-", "LOT-")

    lot = inv.get_or_create_lot(
        db,
        item_id=order.item_id,
        lot_no=lot_no,
        location_id=location.id,
        unit_cost=order.item.standard_cost,
        status=LotStatus.QUARANTINE if needs_qc else LotStatus.AVAILABLE,
        source_order_id=order.id,
    )
    lot.status = LotStatus.QUARANTINE if needs_qc else LotStatus.AVAILABLE

    inv.post_movement(
        db,
        movement_type=MovementType.PRODUCTION_RECEIPT,
        item_id=order.item_id,
        qty=qty,
        lot_no=lot_no,
        to_location_id=location.id,
        unit_cost=order.item.standard_cost,
        ref_type="PRODUCTION_ORDER",
        ref_id=order.id,
        ref_no=order.order_no,
        user_id=user_id,
        note=f"Output of {order.order_no}",
    )


def close_order(db: Session, order: ProductionOrder) -> ProductionOrder:
    if order.status not in (OrderStatus.COMPLETED, OrderStatus.IN_PROGRESS):
        raise ProductionError(f"Order {order.order_no} cannot be closed from {order.status}.")
    order.status = OrderStatus.CLOSED
    order.actual_end = order.actual_end or datetime.now()
    db.flush()
    return order


def cancel_order(db: Session, order: ProductionOrder) -> ProductionOrder:
    if order.qty_produced > 0:
        raise ProductionError("Cannot cancel an order that has already produced output - close it instead.")
    order.status = OrderStatus.CANCELLED
    db.flush()
    return order
