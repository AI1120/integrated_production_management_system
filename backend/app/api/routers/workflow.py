"""Process & status map.

One call that answers "what does the workflow look like, and where is everything
in it right now?" — the end-to-end material pipeline plus every state machine in
the system with a live count on each state.

Every status is zero-filled from the enum rather than derived from whatever rows
happen to exist, so a state with nothing in it still appears on the diagram. A
status that silently vanishes when empty is worse than useless on a wall board.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...enums import (
    Disposition,
    Judgment,
    LocationType,
    LotStatus,
    MachineStatus,
    NcrStatus,
    OperationStatus,
    OrderStatus,
)
from ...models.equipment import Machine
from ...models.inventory import StockLot
from ...models.master import Location
from ...models.production import OrderOperation, ProductionOrder
from ...models.quality import Inspection, NonConformance
from ...models.user import User
from ...schemas.workflow import (
    FlowStage,
    StatusNode,
    WorkflowEntity,
    WorkflowMap,
)
from ..deps import get_current_user

router = APIRouter(prefix="/workflow", tags=["workflow"])


def _counts(db: Session, column, model) -> dict:
    """Group-by count keyed by the enum value."""
    rows = db.execute(select(column, func.count(model.id)).group_by(column)).all()
    return {str(value): int(count) for value, count in rows}


def _nodes(enum_cls, counts: dict, labels: dict[str, str], terminal: set[str] | None = None) -> list[StatusNode]:
    """Zero-fill every member of ``enum_cls`` so no state is hidden when empty."""
    terminal = terminal or set()
    return [
        StatusNode(
            key=member.value,
            label=labels.get(member.value, member.value.replace("_", " ").title()),
            count=counts.get(member.value, 0),
            terminal=member.value in terminal,
        )
        for member in enum_cls
    ]


@router.get("", response_model=WorkflowMap)
def workflow_map(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> WorkflowMap:
    # --- state machines ----------------------------------------------------
    order_counts = _counts(db, ProductionOrder.status, ProductionOrder)
    operation_counts = _counts(db, OrderOperation.status, OrderOperation)
    machine_counts = _counts(db, Machine.status, Machine)
    inspection_counts = _counts(db, Inspection.result, Inspection)
    ncr_counts = _counts(db, NonConformance.status, NonConformance)
    disposition_counts = _counts(db, NonConformance.disposition, NonConformance)

    # Lots only count while they still hold stock - a consumed lot is history.
    lot_rows = db.execute(
        select(StockLot.status, func.count(StockLot.id))
        .where(StockLot.qty > 0)
        .group_by(StockLot.status)
    ).all()
    lot_counts = {str(value): int(count) for value, count in lot_rows}

    entities = [
        WorkflowEntity(
            key="production_order",
            label="Production order",
            hint="Set at release, driven by confirmations, closed by the planner",
            statuses=_nodes(
                OrderStatus,
                order_counts,
                {
                    "DRAFT": "Draft",
                    "RELEASED": "Released",
                    "IN_PROGRESS": "In progress",
                    "COMPLETED": "Completed",
                    "CLOSED": "Closed",
                    "CANCELLED": "Cancelled",
                },
                terminal={"CLOSED", "CANCELLED"},
            ),
            main_path=["DRAFT", "RELEASED", "IN_PROGRESS", "COMPLETED", "CLOSED"],
            branches=[{"from": "DRAFT", "to": "CANCELLED", "label": "cancel"}],
        ),
        WorkflowEntity(
            key="operation",
            label="Routing operation",
            hint="Re-derived from booked quantities on every confirmation",
            statuses=_nodes(
                OperationStatus,
                operation_counts,
                {"PENDING": "Pending", "SETUP": "Setup", "RUNNING": "Running",
                 "PAUSED": "Paused", "COMPLETED": "Completed", "SKIPPED": "Skipped"},
                terminal={"COMPLETED", "SKIPPED"},
            ),
            main_path=["PENDING", "SETUP", "RUNNING", "COMPLETED"],
            branches=[
                {"from": "RUNNING", "to": "PAUSED", "label": "hold"},
                {"from": "PENDING", "to": "SKIPPED", "label": "skip"},
            ],
        ),
        WorkflowEntity(
            key="stock_lot",
            label="Stock lot",
            hint="Output lands in quarantine when the routing requires inspection",
            statuses=_nodes(
                LotStatus,
                lot_counts,
                {"AVAILABLE": "Available", "QUARANTINE": "Quarantine",
                 "REJECTED": "Rejected", "CONSUMED": "Consumed"},
                terminal={"CONSUMED", "REJECTED"},
            ),
            main_path=["QUARANTINE", "AVAILABLE", "CONSUMED"],
            branches=[{"from": "QUARANTINE", "to": "REJECTED", "label": "inspection fails"}],
        ),
        WorkflowEntity(
            key="inspection",
            label="Inspection",
            hint="Judged automatically against the plan's limits",
            statuses=_nodes(
                Judgment,
                inspection_counts,
                {"PENDING": "Pending", "PASS": "Pass", "FAIL": "Fail"},
                terminal={"PASS", "FAIL"},
            ),
            main_path=["PENDING", "PASS"],
            branches=[{"from": "PENDING", "to": "FAIL", "label": "out of spec"}],
        ),
        WorkflowEntity(
            key="ncr",
            label="Non-conformance",
            hint="Raised automatically when an inspection fails",
            statuses=_nodes(
                NcrStatus,
                ncr_counts,
                {"OPEN": "Open", "IN_REVIEW": "In review", "CLOSED": "Closed"},
                terminal={"CLOSED"},
            ),
            main_path=["OPEN", "IN_REVIEW", "CLOSED"],
            branches=[],
        ),
        WorkflowEntity(
            key="disposition",
            label="NCR disposition",
            hint="Choosing Scrap writes the quantity off stock immediately",
            statuses=_nodes(
                Disposition,
                disposition_counts,
                {"PENDING": "Pending", "REWORK": "Rework", "SCRAP": "Scrap",
                 "USE_AS_IS": "Use as is", "RETURN_TO_SUPPLIER": "Return to supplier"},
                terminal={"SCRAP", "USE_AS_IS", "RETURN_TO_SUPPLIER"},
            ),
            main_path=["PENDING"],
            branches=[
                {"from": "PENDING", "to": "REWORK", "label": "rework"},
                {"from": "PENDING", "to": "SCRAP", "label": "scrap"},
                {"from": "PENDING", "to": "USE_AS_IS", "label": "concession"},
                {"from": "PENDING", "to": "RETURN_TO_SUPPLIER", "label": "return"},
            ],
        ),
        WorkflowEntity(
            key="machine",
            label="Machine",
            hint=(
                "A stop opens a downtime event and takes the machine out of the "
                "schedule until it is expected back; a restart closes both"
            ),
            statuses=_nodes(
                MachineStatus,
                machine_counts,
                {"IDLE": "Idle", "SETUP": "Setup", "RUNNING": "Running",
                 "DOWN": "Down", "MAINTENANCE": "Maintenance"},
            ),
            main_path=["IDLE", "SETUP", "RUNNING"],
            # Both stops are entered straight from the board, which is what the
            # stop dialog actually does - it offers Down or Maintenance directly.
            branches=[
                {"from": "RUNNING", "to": "DOWN", "label": "breakdown"},
                {"from": "RUNNING", "to": "MAINTENANCE", "label": "planned stop"},
            ],
            returns=[
                {"from": "DOWN", "to": "IDLE", "label": "repaired"},
                {"from": "MAINTENANCE", "to": "IDLE", "label": "back in service"},
            ],
        ),
    ]

    # --- end-to-end material pipeline --------------------------------------
    def lots_at(location_type: LocationType, status: LotStatus) -> tuple[int, float]:
        row = db.execute(
            select(func.count(StockLot.id), func.coalesce(func.sum(StockLot.qty), 0.0))
            .join(Location, StockLot.location_id == Location.id)
            .where(
                Location.location_type == location_type,
                StockLot.status == status,
                StockLot.qty > 0,
            )
        ).one()
        return int(row[0] or 0), float(row[1] or 0.0)

    raw_lots, raw_qty = lots_at(LocationType.RAW, LotStatus.AVAILABLE)
    qc_lots, qc_qty = lots_at(LocationType.QUARANTINE, LotStatus.QUARANTINE)
    fg_lots, fg_qty = lots_at(LocationType.FINISHED, LotStatus.AVAILABLE)

    def orders_in(*statuses: OrderStatus) -> int:
        return int(
            db.scalar(
                select(func.count(ProductionOrder.id)).where(ProductionOrder.status.in_(statuses))
            )
            or 0
        )

    rejected_lots = int(
        db.scalar(
            select(func.count(StockLot.id)).where(
                StockLot.status == LotStatus.REJECTED, StockLot.qty > 0
            )
        )
        or 0
    )
    open_ncrs = int(
        db.scalar(select(func.count(NonConformance.id)).where(NonConformance.status != NcrStatus.CLOSED))
        or 0
    )

    flow = [
        FlowStage(key="supply", label="Raw store", detail="Lots available to pick",
                  count=raw_lots, unit="lots", secondary=round(raw_qty, 1), kind="store"),
        FlowStage(key="plan", label="Planned", detail="Drafted, not yet on the floor",
                  count=orders_in(OrderStatus.DRAFT), unit="orders", kind="gate"),
        FlowStage(key="release", label="Released", detail="Kitted and queued",
                  count=orders_in(OrderStatus.RELEASED), unit="orders", kind="gate"),
        FlowStage(key="produce", label="In production", detail="Booking against operations",
                  count=orders_in(OrderStatus.IN_PROGRESS), unit="orders", kind="process"),
        FlowStage(key="quarantine", label="Awaiting QC", detail="Output held pending inspection",
                  count=qc_lots, unit="lots", secondary=round(qc_qty, 1), kind="gate"),
        FlowStage(key="finished", label="Finished store", detail="Released, ready to ship",
                  count=fg_lots, unit="lots", secondary=round(fg_qty, 1), kind="store"),
    ]
    reject_branch = [
        FlowStage(key="rejected", label="Rejected", detail="Blocked by a failed inspection",
                  count=rejected_lots, unit="lots", kind="reject"),
        FlowStage(key="ncr", label="Open NCRs", detail="Awaiting a disposition",
                  count=open_ncrs, unit="NCRs", kind="reject"),
    ]

    return WorkflowMap(
        generated_at=datetime.now(),
        flow=flow,
        reject_branch=reject_branch,
        entities=entities,
    )
