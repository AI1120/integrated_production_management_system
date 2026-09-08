"""Stock engine.

Every quantity change in the system goes through :func:`post_movement`, which
updates the affected :class:`StockLot` rows and appends one immutable
:class:`StockMovement` ledger row. Nothing else is allowed to write ``qty``.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..enums import ItemType, LocationType, LotStatus, MovementType
from ..models.inventory import StockLot, StockMovement
from ..models.master import Item, Location


class StockError(Exception):
    """Raised when a movement would leave stock in an impossible state."""


# Movements that add to a location, remove from one, or both.
_ADDS_TO = {
    MovementType.RECEIPT,
    MovementType.PRODUCTION_RECEIPT,
    MovementType.TRANSFER,
    MovementType.RETURN,
    MovementType.ADJUSTMENT,
}
_REMOVES_FROM = {
    MovementType.ISSUE,
    MovementType.SCRAP,
    MovementType.TRANSFER,
}


def get_or_create_lot(
    db: Session,
    *,
    item_id: int,
    lot_no: str,
    location_id: int,
    unit_cost: float = 0.0,
    status: LotStatus = LotStatus.AVAILABLE,
    **extra,
) -> StockLot:
    lot = db.scalar(
        select(StockLot).where(
            StockLot.item_id == item_id,
            StockLot.lot_no == lot_no,
            StockLot.location_id == location_id,
        )
    )
    if lot is None:
        lot = StockLot(
            item_id=item_id,
            lot_no=lot_no,
            location_id=location_id,
            qty=0.0,
            unit_cost=unit_cost,
            status=status,
            received_at=datetime.now(),
            **extra,
        )
        db.add(lot)
        db.flush()
    return lot


def post_movement(
    db: Session,
    *,
    movement_type: MovementType,
    item_id: int,
    qty: float,
    lot_no: str | None = None,
    from_location_id: int | None = None,
    to_location_id: int | None = None,
    unit_cost: float = 0.0,
    ref_type: str | None = None,
    ref_id: int | None = None,
    ref_no: str | None = None,
    user_id: int | None = None,
    note: str | None = None,
    occurred_at: datetime | None = None,
    allow_negative: bool = False,
) -> StockMovement:
    """Apply one stock movement and record it in the ledger.

    ``qty`` is always positive except for ADJUSTMENT, where a negative value
    means a write-down.
    """
    if movement_type is not MovementType.ADJUSTMENT and qty <= 0:
        raise StockError("Quantity must be greater than zero.")

    item = db.get(Item, item_id)
    if item is None:
        raise StockError(f"Unknown item id {item_id}.")

    if item.is_lot_controlled and not lot_no:
        raise StockError(f"Item {item.code} is lot controlled - a lot number is required.")
    lot_no = lot_no or "NOLOT"

    if movement_type in _REMOVES_FROM and from_location_id is None:
        raise StockError(f"{movement_type} requires a source location.")
    if movement_type in _ADDS_TO and movement_type is not MovementType.ADJUSTMENT and to_location_id is None:
        raise StockError(f"{movement_type} requires a destination location.")

    # --- outbound leg ---
    if movement_type in _REMOVES_FROM:
        source = db.scalar(
            select(StockLot).where(
                StockLot.item_id == item_id,
                StockLot.lot_no == lot_no,
                StockLot.location_id == from_location_id,
            )
        )
        if source is None:
            raise StockError(f"No stock of {item.code} lot {lot_no} at the source location.")
        if source.qty < qty and not allow_negative:
            raise StockError(
                f"Insufficient stock: {item.code} lot {lot_no} has {source.qty:g} {item.uom}, "
                f"needs {qty:g} {item.uom}."
            )
        source.qty -= qty
        unit_cost = unit_cost or source.unit_cost
        if source.qty <= 0:
            source.status = LotStatus.CONSUMED

    # --- inbound leg ---
    if movement_type in _ADDS_TO:
        target_location = to_location_id if to_location_id is not None else from_location_id
        if target_location is None:
            raise StockError(f"{movement_type} requires a location.")
        target = get_or_create_lot(
            db,
            item_id=item_id,
            lot_no=lot_no,
            location_id=target_location,
            unit_cost=unit_cost or item.standard_cost,
        )
        new_qty = target.qty + qty
        if new_qty < 0 and not allow_negative:
            raise StockError(f"Adjustment would drive {item.code} lot {lot_no} negative.")
        # Weighted-average cost on inbound quantity.
        if qty > 0 and unit_cost:
            total_value = target.qty * target.unit_cost + qty * unit_cost
            target.unit_cost = total_value / new_qty if new_qty else unit_cost
        target.qty = new_qty
        if target.qty > 0 and target.status is LotStatus.CONSUMED:
            target.status = LotStatus.AVAILABLE

    movement = StockMovement(
        movement_type=movement_type,
        item_id=item_id,
        lot_no=lot_no,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        qty=qty,
        unit_cost=unit_cost,
        ref_type=ref_type,
        ref_id=ref_id,
        ref_no=ref_no,
        user_id=user_id,
        occurred_at=occurred_at or datetime.now(),
        note=note,
    )
    db.add(movement)
    db.flush()
    return movement


def allocate_fifo(db: Session, *, item_id: int, qty: float, location_id: int | None = None) -> list[tuple[StockLot, float]]:
    """Pick lots oldest-first to cover ``qty``. Returns [(lot, qty_from_lot), ...].

    Raises :class:`StockError` if available stock cannot cover the request, so the
    caller never issues a partial pick by accident.
    """
    stmt = (
        select(StockLot)
        .where(
            StockLot.item_id == item_id,
            StockLot.qty > 0,
            StockLot.status == LotStatus.AVAILABLE,
        )
        .order_by(StockLot.received_at.asc(), StockLot.id.asc())
    )
    if location_id is not None:
        stmt = stmt.where(StockLot.location_id == location_id)

    picks: list[tuple[StockLot, float]] = []
    remaining = qty
    for lot in db.scalars(stmt):
        if remaining <= 1e-9:
            break
        take = min(lot.qty, remaining)
        picks.append((lot, take))
        remaining -= take

    if remaining > 1e-9:
        item = db.get(Item, item_id)
        available = qty - remaining
        raise StockError(
            f"Insufficient stock for {item.code if item else item_id}: "
            f"available {available:g}, required {qty:g}."
        )
    return picks


def on_hand(db: Session, item_id: int, location_id: int | None = None) -> float:
    stmt = select(func.coalesce(func.sum(StockLot.qty), 0.0)).where(
        StockLot.item_id == item_id,
        StockLot.status == LotStatus.AVAILABLE,
    )
    if location_id is not None:
        stmt = stmt.where(StockLot.location_id == location_id)
    return float(db.scalar(stmt) or 0.0)


def stock_location_for(db: Session, item: Item) -> Location:
    """Where finished output of ``item`` belongs once it is cleared for use.

    Sub-assemblies go back to the component store so the next order can consume
    them; finished goods go to the despatch store.
    """
    if item.item_type is ItemType.SUB_ASSEMBLY:
        return default_location(db, LocationType.RAW)
    return default_location(db, LocationType.FINISHED)


def default_location(db: Session, location_type: LocationType) -> Location:
    location = db.scalar(
        select(Location).where(Location.location_type == location_type, Location.is_active.is_(True)).limit(1)
    )
    if location is None:
        raise StockError(f"No active {location_type} location is configured.")
    return location
