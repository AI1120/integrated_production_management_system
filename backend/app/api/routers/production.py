"""Work orders, shop-floor confirmations and barcode scan resolution."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...enums import OperationStatus, OrderStatus, Role
from ...models.inventory import StockLot
from ...models.master import Item
from ...models.production import Confirmation, OrderMaterial, OrderOperation, ProductionOrder
from ...models.user import User
from ...schemas.production import (
    ConfirmationCreate,
    ConfirmationRead,
    MaterialIssue,
    OrderOperationRead,
    ProductionOrderCreate,
    ProductionOrderDetail,
    ProductionOrderRead,
    ScanLookup,
    ScanResult,
)
from ...services import inventory_service as inv
from ...services import production_service as prod
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/production", tags=["production"])

Planner = Depends(require_roles(Role.PLANNER))
Operator = Depends(require_roles(Role.OPERATOR, Role.PLANNER))
AnyUser = Depends(get_current_user)


def _load_order(db: Session, order_id: int) -> ProductionOrder:
    order = db.scalar(
        select(ProductionOrder)
        .options(
            selectinload(ProductionOrder.operations).selectinload(OrderOperation.work_center),
            selectinload(ProductionOrder.materials).selectinload(OrderMaterial.component),
            selectinload(ProductionOrder.item),
        )
        .where(ProductionOrder.id == order_id)
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production order not found")
    return order


@router.get("/orders", response_model=list[ProductionOrderRead])
def list_orders(
    status_filter: OrderStatus | None = None,
    item_id: int | None = None,
    open_only: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[ProductionOrder]:
    stmt = select(ProductionOrder).options(selectinload(ProductionOrder.item))
    if status_filter:
        stmt = stmt.where(ProductionOrder.status == status_filter)
    if open_only:
        stmt = stmt.where(
            ProductionOrder.status.in_([OrderStatus.RELEASED, OrderStatus.IN_PROGRESS])
        )
    if item_id:
        stmt = stmt.where(ProductionOrder.item_id == item_id)
    stmt = stmt.order_by(ProductionOrder.priority.asc(), ProductionOrder.id.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/orders/{order_id}", response_model=ProductionOrderDetail)
def get_order(order_id: int, db: Session = Depends(get_db), _: User = AnyUser) -> ProductionOrder:
    return _load_order(db, order_id)


@router.post("/orders", response_model=ProductionOrderDetail, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: ProductionOrderCreate, db: Session = Depends(get_db), _: User = Planner
) -> ProductionOrder:
    try:
        order = prod.create_order(
            db,
            item_id=payload.item_id,
            qty=payload.qty_ordered,
            bom_id=payload.bom_id,
            routing_id=payload.routing_id,
            planned_start=payload.planned_start,
            planned_end=payload.planned_end,
            due_date=payload.due_date,
            priority=payload.priority,
            customer_id=payload.customer_id,
            sales_ref=payload.sales_ref,
            note=payload.note,
        )
    except prod.ProductionError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _load_order(db, order.id)


@router.post("/orders/{order_id}/release", response_model=ProductionOrderDetail)
def release_order(order_id: int, db: Session = Depends(get_db), _: User = Planner) -> ProductionOrder:
    order = _load_order(db, order_id)
    try:
        prod.release_order(db, order)
    except prod.ProductionError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    return _load_order(db, order_id)


@router.post("/orders/{order_id}/close", response_model=ProductionOrderDetail)
def close_order(order_id: int, db: Session = Depends(get_db), _: User = Planner) -> ProductionOrder:
    order = _load_order(db, order_id)
    try:
        prod.close_order(db, order)
    except prod.ProductionError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    return _load_order(db, order_id)


@router.post("/orders/{order_id}/cancel", response_model=ProductionOrderDetail)
def cancel_order(order_id: int, db: Session = Depends(get_db), _: User = Planner) -> ProductionOrder:
    order = _load_order(db, order_id)
    try:
        prod.cancel_order(db, order)
    except prod.ProductionError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    return _load_order(db, order_id)


@router.post("/orders/{order_id}/issue", response_model=ProductionOrderDetail)
def issue_material(
    order_id: int,
    payload: MaterialIssue,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.OPERATOR, Role.WAREHOUSE, Role.PLANNER)),
) -> ProductionOrder:
    order = _load_order(db, order_id)
    material = db.get(OrderMaterial, payload.material_id)
    if material is None or material.order_id != order.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material line not found on this order")

    try:
        prod.issue_material(
            db,
            order=order,
            material=material,
            qty=payload.qty,
            lot_no=payload.lot_no,
            from_location_id=payload.from_location_id,
            user_id=user.id,
        )
    except (prod.ProductionError, inv.StockError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _load_order(db, order_id)


@router.post("/confirmations", response_model=ConfirmationRead, status_code=status.HTTP_201_CREATED)
def confirm_operation(
    payload: ConfirmationCreate,
    db: Session = Depends(get_db),
    user: User = Operator,
) -> Confirmation:
    operation = db.get(OrderOperation, payload.operation_id)
    if operation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Operation not found")

    try:
        confirmation = prod.confirm_operation(
            db,
            operation=operation,
            qty_good=payload.qty_good,
            qty_scrap=payload.qty_scrap,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            operator_id=user.id,
            defect_code_id=payload.defect_code_id,
            machine_id=payload.machine_id,
            note=payload.note,
        )
    except (prod.ProductionError, inv.StockError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(confirmation)
    return confirmation


@router.get("/confirmations", response_model=list[ConfirmationRead])
def list_confirmations(
    order_id: int | None = None,
    operation_id: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[Confirmation]:
    stmt = select(Confirmation)
    if operation_id:
        stmt = stmt.where(Confirmation.operation_id == operation_id)
    if order_id:
        stmt = stmt.join(OrderOperation).where(OrderOperation.order_id == order_id)
    return list(db.scalars(stmt.order_by(Confirmation.ended_at.desc()).limit(limit)))


@router.get("/queue", response_model=list[OrderOperationRead])
def work_queue(
    work_center_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[OrderOperation]:
    """Operations still to run, ordered the way the floor should take them."""
    stmt = (
        select(OrderOperation)
        .options(selectinload(OrderOperation.work_center))
        .join(ProductionOrder)
        .where(
            ProductionOrder.status.in_([OrderStatus.RELEASED, OrderStatus.IN_PROGRESS]),
            OrderOperation.status != OperationStatus.COMPLETED,
        )
        .order_by(ProductionOrder.priority.asc(), ProductionOrder.planned_start.asc(), OrderOperation.seq.asc())
    )
    if work_center_id:
        stmt = stmt.where(OrderOperation.work_center_id == work_center_id)
    return list(db.scalars(stmt))


@router.post("/scan", response_model=ScanResult)
def resolve_scan(payload: ScanLookup, db: Session = Depends(get_db), _: User = AnyUser) -> ScanResult:
    """Turn one scanned barcode into whatever the terminal should show next.

    The scanner behaves as a keyboard, so a single endpoint has to disambiguate
    order numbers, item codes, lot numbers and operator badges.
    """
    code = payload.code.strip()

    order = db.scalar(select(ProductionOrder).where(ProductionOrder.order_no == code))
    if order:
        return ScanResult(
            kind="ORDER",
            id=order.id,
            label=f"{order.order_no} - {order.item.name}",
            payload={"status": order.status, "qty_ordered": order.qty_ordered, "qty_produced": order.qty_produced},
        )

    item = db.scalar(select(Item).where(Item.code == code))
    if item:
        return ScanResult(
            kind="ITEM",
            id=item.id,
            label=f"{item.code} - {item.name}",
            payload={"uom": item.uom, "on_hand": inv.on_hand(db, item.id)},
        )

    lot = db.scalar(select(StockLot).where(StockLot.lot_no == code, StockLot.qty > 0))
    if lot:
        return ScanResult(
            kind="LOT",
            id=lot.id,
            label=f"{lot.lot_no} - {lot.item.code}",
            payload={
                "item_id": lot.item_id,
                "qty": lot.qty,
                "location_id": lot.location_id,
                "status": lot.status,
            },
        )

    badge = db.scalar(select(User).where(User.badge_no == code))
    if badge:
        return ScanResult(kind="BADGE", id=badge.id, label=badge.full_name, payload={"role": badge.role})

    return ScanResult(kind="UNKNOWN", label=f"Nothing matches {code}", payload={})
