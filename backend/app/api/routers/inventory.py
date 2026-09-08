"""Stock enquiry and warehouse transactions."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...enums import LocationType, LotStatus, MovementType, Role
from ...models.inventory import StockLot, StockMovement
from ...models.master import Item
from ...models.user import User
from ...schemas.inventory import (
    GoodsReceipt,
    StockAdjustment,
    StockLotRead,
    StockMovementRead,
    StockOnHand,
    StockTransfer,
)
from ...services import inventory_service as inv
from ...services.numbering import next_number
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/inventory", tags=["inventory"])

Warehouse = Depends(require_roles(Role.WAREHOUSE, Role.PLANNER))
AnyUser = Depends(get_current_user)


@router.get("/on-hand", response_model=list[StockOnHand])
def on_hand_summary(
    low_stock_only: bool = False, db: Session = Depends(get_db), _: User = AnyUser
) -> list[StockOnHand]:
    rows = db.execute(
        select(
            Item,
            func.coalesce(func.sum(StockLot.qty), 0.0),
            func.count(StockLot.id),
            func.coalesce(func.sum(StockLot.qty * StockLot.unit_cost), 0.0),
        )
        .outerjoin(
            StockLot,
            (StockLot.item_id == Item.id) & (StockLot.status == LotStatus.AVAILABLE) & (StockLot.qty > 0),
        )
        .where(Item.is_active.is_(True))
        .group_by(Item.id)
        .order_by(Item.code)
    ).all()

    summary = [
        StockOnHand(
            item_id=item.id,
            item_code=item.code,
            item_name=item.name,
            uom=item.uom,
            on_hand=round(float(qty or 0.0), 4),
            safety_stock=item.safety_stock,
            below_safety_stock=float(qty or 0.0) < item.safety_stock,
            lot_count=int(lots or 0),
            value=round(float(value or 0.0), 2),
        )
        for item, qty, lots, value in rows
    ]
    return [row for row in summary if row.below_safety_stock] if low_stock_only else summary


@router.get("/lots", response_model=list[StockLotRead])
def list_lots(
    item_id: int | None = None,
    location_id: int | None = None,
    lot_no: str | None = None,
    status_filter: LotStatus | None = None,
    with_stock_only: bool = True,
    limit: int = 300,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[StockLot]:
    stmt = select(StockLot).options(selectinload(StockLot.item), selectinload(StockLot.location))
    if item_id:
        stmt = stmt.where(StockLot.item_id == item_id)
    if location_id:
        stmt = stmt.where(StockLot.location_id == location_id)
    if lot_no:
        stmt = stmt.where(StockLot.lot_no.ilike(f"%{lot_no}%"))
    if status_filter:
        stmt = stmt.where(StockLot.status == status_filter)
    if with_stock_only:
        stmt = stmt.where(StockLot.qty > 0)
    return list(db.scalars(stmt.order_by(StockLot.item_id, StockLot.received_at).limit(limit)))


@router.get("/movements", response_model=list[StockMovementRead])
def list_movements(
    item_id: int | None = None,
    lot_no: str | None = None,
    movement_type: MovementType | None = None,
    ref_no: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[StockMovement]:
    stmt = select(StockMovement).options(selectinload(StockMovement.item))
    if item_id:
        stmt = stmt.where(StockMovement.item_id == item_id)
    if lot_no:
        stmt = stmt.where(StockMovement.lot_no == lot_no)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type)
    if ref_no:
        stmt = stmt.where(StockMovement.ref_no == ref_no)
    return list(db.scalars(stmt.order_by(StockMovement.occurred_at.desc(), StockMovement.id.desc()).limit(limit)))


@router.post("/receipts", response_model=StockLotRead, status_code=status.HTTP_201_CREATED)
def goods_receipt(payload: GoodsReceipt, db: Session = Depends(get_db), user: User = Warehouse) -> StockLot:
    """Book incoming material. Lot numbers are generated when not supplied."""
    item = db.get(Item, payload.item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    lot_no = payload.lot_no or next_number(db, "RCV")
    try:
        location_id = payload.location_id or inv.default_location(db, LocationType.RAW).id
        inv.post_movement(
            db,
            movement_type=MovementType.RECEIPT,
            item_id=item.id,
            qty=payload.qty,
            lot_no=lot_no,
            to_location_id=location_id,
            unit_cost=payload.unit_cost or item.standard_cost,
            ref_type="GOODS_RECEIPT",
            ref_no=lot_no,
            user_id=user.id,
            note=payload.note,
        )
    except inv.StockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    lot = db.scalar(
        select(StockLot).where(
            StockLot.item_id == item.id, StockLot.lot_no == lot_no, StockLot.location_id == location_id
        )
    )
    if payload.supplier_id:
        lot.supplier_id = payload.supplier_id
    if payload.expiry_date:
        lot.expiry_date = payload.expiry_date
    db.commit()
    db.refresh(lot)
    return lot


@router.post("/transfers", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
def transfer(payload: StockTransfer, db: Session = Depends(get_db), user: User = Warehouse) -> StockMovement:
    if payload.from_location_id == payload.to_location_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Source and destination must differ")
    try:
        movement = inv.post_movement(
            db,
            movement_type=MovementType.TRANSFER,
            item_id=payload.item_id,
            qty=payload.qty,
            lot_no=payload.lot_no,
            from_location_id=payload.from_location_id,
            to_location_id=payload.to_location_id,
            ref_type="TRANSFER",
            user_id=user.id,
            note=payload.note,
        )
    except inv.StockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(movement)
    return movement


@router.post("/adjustments", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
def adjust(payload: StockAdjustment, db: Session = Depends(get_db), user: User = Warehouse) -> StockMovement:
    """Signed correction against a counted lot. The reason is mandatory - it is the audit trail."""
    if payload.qty == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Adjustment quantity cannot be zero")
    try:
        movement = inv.post_movement(
            db,
            movement_type=MovementType.ADJUSTMENT,
            item_id=payload.item_id,
            qty=payload.qty,
            lot_no=payload.lot_no,
            to_location_id=payload.location_id,
            ref_type="ADJUSTMENT",
            user_id=user.id,
            note=payload.reason,
        )
    except inv.StockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(movement)
    return movement


@router.get("/trace/{lot_no}")
def trace_lot(lot_no: str, db: Session = Depends(get_db), _: User = AnyUser) -> dict:
    """Genealogy for one lot: where it sits now, and every movement that touched it.

    For a produced lot this also lists the component lots consumed by its order -
    the backward trace an audit or a recall starts from.
    """
    lots = list(
        db.scalars(
            select(StockLot)
            .options(selectinload(StockLot.item), selectinload(StockLot.location))
            .where(StockLot.lot_no == lot_no)
        )
    )
    if not lots:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Lot {lot_no} not found")

    movements = list(
        db.scalars(
            select(StockMovement)
            .options(selectinload(StockMovement.item))
            .where(StockMovement.lot_no == lot_no)
            .order_by(StockMovement.occurred_at)
        )
    )

    consumed: list[dict] = []
    source_order_id = next((lot.source_order_id for lot in lots if lot.source_order_id), None)
    if source_order_id:
        for movement in db.scalars(
            select(StockMovement)
            .options(selectinload(StockMovement.item))
            .where(
                StockMovement.ref_type == "PRODUCTION_ORDER",
                StockMovement.ref_id == source_order_id,
                StockMovement.movement_type == MovementType.ISSUE,
            )
        ):
            consumed.append(
                {
                    "item_code": movement.item.code,
                    "item_name": movement.item.name,
                    "lot_no": movement.lot_no,
                    "qty": movement.qty,
                    "occurred_at": movement.occurred_at,
                }
            )

    return {
        "lot_no": lot_no,
        "source_order_id": source_order_id,
        "current_stock": [StockLotRead.model_validate(lot).model_dump() for lot in lots],
        "movements": [StockMovementRead.model_validate(m).model_dump() for m in movements],
        "consumed_components": consumed,
    }
