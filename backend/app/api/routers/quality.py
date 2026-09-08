"""Inspection plans, inspections and non-conformance reports."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...enums import (
    CharacteristicType,
    Disposition,
    InspectionType,
    Judgment,
    LocationType,
    LotStatus,
    MovementType,
    NcrStatus,
    Role,
)
from ...models.inventory import StockLot
from ...models.master import Item
from ...models.quality import (
    DefectCode,
    Inspection,
    InspectionCharacteristic,
    InspectionPlan,
    InspectionResult,
    NonConformance,
)
from ...models.user import User
from ...schemas.quality import (
    DefectCodeCreate,
    DefectCodeRead,
    InspectionCreate,
    InspectionPlanCreate,
    InspectionPlanRead,
    InspectionRead,
    NcrCreate,
    NcrRead,
    NcrUpdate,
)
from ...services import inventory_service as inv
from ...services.numbering import next_number
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/quality", tags=["quality"])

Inspector = Depends(require_roles(Role.QC))
AnyUser = Depends(get_current_user)


# --- Defect codes -----------------------------------------------------------
@router.get("/defect-codes", response_model=list[DefectCodeRead])
def list_defect_codes(db: Session = Depends(get_db), _: User = AnyUser) -> list[DefectCode]:
    return list(db.scalars(select(DefectCode).where(DefectCode.is_active.is_(True)).order_by(DefectCode.code)))


@router.post("/defect-codes", response_model=DefectCodeRead, status_code=status.HTTP_201_CREATED)
def create_defect_code(
    payload: DefectCodeCreate, db: Session = Depends(get_db), _: User = Inspector
) -> DefectCode:
    if db.scalar(select(DefectCode).where(DefectCode.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Defect code {payload.code} already exists")
    code = DefectCode(**payload.model_dump())
    db.add(code)
    db.commit()
    db.refresh(code)
    return code


# --- Inspection plans -------------------------------------------------------
@router.get("/plans", response_model=list[InspectionPlanRead])
def list_plans(
    item_id: int | None = None,
    inspection_type: InspectionType | None = None,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[InspectionPlan]:
    stmt = select(InspectionPlan).options(selectinload(InspectionPlan.characteristics))
    if item_id:
        stmt = stmt.where(InspectionPlan.item_id == item_id)
    if inspection_type:
        stmt = stmt.where(InspectionPlan.inspection_type == inspection_type)
    return list(db.scalars(stmt.order_by(InspectionPlan.code)))


@router.post("/plans", response_model=InspectionPlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: InspectionPlanCreate, db: Session = Depends(get_db), _: User = Inspector
) -> InspectionPlan:
    if db.scalar(select(InspectionPlan).where(InspectionPlan.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Plan {payload.code} already exists")
    plan = InspectionPlan(**payload.model_dump(exclude={"characteristics"}))
    db.add(plan)
    db.flush()
    for characteristic in payload.characteristics:
        db.add(InspectionCharacteristic(plan_id=plan.id, **characteristic.model_dump()))
    db.commit()
    db.refresh(plan)
    return plan


# --- Inspections ------------------------------------------------------------
def _judge(characteristic: InspectionCharacteristic | None, value: float | None, text: str | None) -> Judgment:
    """Compare one recorded value with its specification limits."""
    if characteristic is None:
        return Judgment.PASS if value is not None or text else Judgment.PENDING
    if characteristic.char_type is CharacteristicType.ATTRIBUTE:
        return Judgment.PASS if (text or "").strip().upper() in {"OK", "PASS", "GOOD", "Y", "YES"} else Judgment.FAIL
    if value is None:
        return Judgment.PENDING
    if characteristic.lower_limit is not None and value < characteristic.lower_limit:
        return Judgment.FAIL
    if characteristic.upper_limit is not None and value > characteristic.upper_limit:
        return Judgment.FAIL
    return Judgment.PASS


@router.get("/inspections", response_model=list[InspectionRead])
def list_inspections(
    order_id: int | None = None,
    item_id: int | None = None,
    result: Judgment | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[Inspection]:
    stmt = select(Inspection).options(selectinload(Inspection.item), selectinload(Inspection.results))
    if order_id:
        stmt = stmt.where(Inspection.order_id == order_id)
    if item_id:
        stmt = stmt.where(Inspection.item_id == item_id)
    if result:
        stmt = stmt.where(Inspection.result == result)
    return list(db.scalars(stmt.order_by(Inspection.inspected_at.desc()).limit(limit)))


@router.post("/inspections", response_model=InspectionRead, status_code=status.HTTP_201_CREATED)
def record_inspection(
    payload: InspectionCreate, db: Session = Depends(get_db), user: User = Inspector
) -> Inspection:
    """Record an inspection, judge each measurement, and act on the verdict.

    A pass releases the lot out of quarantine; a failure raises an NCR and leaves
    the stock blocked. The inspector never has to remember to do either by hand.
    """
    item = db.get(Item, payload.item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    if payload.qty_rejected > payload.qty_inspected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rejected quantity exceeds inspected quantity")

    inspection = Inspection(
        inspection_no=next_number(db, "INS"),
        plan_id=payload.plan_id,
        inspection_type=payload.inspection_type,
        item_id=item.id,
        lot_no=payload.lot_no,
        order_id=payload.order_id,
        operation_id=payload.operation_id,
        qty_inspected=payload.qty_inspected,
        qty_rejected=payload.qty_rejected,
        qty_accepted=payload.qty_inspected - payload.qty_rejected,
        inspector_id=user.id,
        inspected_at=datetime.now(),
        note=payload.note,
    )
    db.add(inspection)
    db.flush()

    any_fail = False
    for entry in payload.results:
        characteristic = (
            db.get(InspectionCharacteristic, entry.characteristic_id) if entry.characteristic_id else None
        )
        judgment = _judge(characteristic, entry.value_numeric, entry.value_text)
        any_fail = any_fail or judgment is Judgment.FAIL
        db.add(
            InspectionResult(
                inspection_id=inspection.id,
                characteristic_id=entry.characteristic_id,
                characteristic_name=entry.characteristic_name
                or (characteristic.name if characteristic else "Measurement"),
                sample_no=entry.sample_no,
                value_numeric=entry.value_numeric,
                value_text=entry.value_text,
                judgment=judgment,
            )
        )

    inspection.result = Judgment.FAIL if (any_fail or payload.qty_rejected > 0) else Judgment.PASS

    if inspection.lot_no:
        _apply_lot_verdict(db, inspection, user)

    if inspection.result is Judgment.FAIL:
        db.add(
            NonConformance(
                ncr_no=next_number(db, "NCR"),
                item_id=item.id,
                lot_no=inspection.lot_no,
                order_id=inspection.order_id,
                inspection_id=inspection.id,
                qty=payload.qty_rejected or payload.qty_inspected,
                description=f"Raised automatically from inspection {inspection.inspection_no}",
                raised_by_id=user.id,
            )
        )

    db.commit()
    db.refresh(inspection)
    return inspection


def _apply_lot_verdict(db: Session, inspection: Inspection, user: User) -> None:
    """Release a passed lot into finished stock, or block a failed one."""
    lots = list(
        db.scalars(
            select(StockLot).where(StockLot.item_id == inspection.item_id, StockLot.lot_no == inspection.lot_no)
        )
    )
    if not lots:
        return

    if inspection.result is Judgment.FAIL:
        for lot in lots:
            if lot.status is LotStatus.QUARANTINE:
                lot.status = LotStatus.REJECTED
        return

    finished = inv.stock_location_for(db, db.get(Item, inspection.item_id))
    for lot in lots:
        if lot.status is not LotStatus.QUARANTINE or lot.qty <= 0:
            continue
        if lot.location_id == finished.id:
            lot.status = LotStatus.AVAILABLE
            continue
        qty = lot.qty
        source_location = lot.location_id
        lot.status = LotStatus.AVAILABLE  # allow the outbound leg to find it
        inv.post_movement(
            db,
            movement_type=MovementType.TRANSFER,
            item_id=lot.item_id,
            qty=qty,
            lot_no=lot.lot_no,
            from_location_id=source_location,
            to_location_id=finished.id,
            ref_type="INSPECTION",
            ref_id=inspection.id,
            ref_no=inspection.inspection_no,
            user_id=user.id,
            note="Released from quarantine after passing inspection",
        )


# --- Non-conformance --------------------------------------------------------
@router.get("/ncrs", response_model=list[NcrRead])
def list_ncrs(
    status_filter: NcrStatus | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[NonConformance]:
    stmt = select(NonConformance).options(
        selectinload(NonConformance.item), selectinload(NonConformance.defect_code)
    )
    if status_filter:
        stmt = stmt.where(NonConformance.status == status_filter)
    return list(db.scalars(stmt.order_by(NonConformance.id.desc()).limit(limit)))


@router.post("/ncrs", response_model=NcrRead, status_code=status.HTTP_201_CREATED)
def create_ncr(payload: NcrCreate, db: Session = Depends(get_db), user: User = Inspector) -> NonConformance:
    if db.get(Item, payload.item_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    ncr = NonConformance(ncr_no=next_number(db, "NCR"), raised_by_id=user.id, **payload.model_dump())
    db.add(ncr)
    db.commit()
    db.refresh(ncr)
    return ncr


@router.patch("/ncrs/{ncr_id}", response_model=NcrRead)
def update_ncr(
    ncr_id: int, payload: NcrUpdate, db: Session = Depends(get_db), user: User = Inspector
) -> NonConformance:
    """Set a disposition. Choosing SCRAP writes the quantity off stock immediately."""
    ncr = db.get(NonConformance, ncr_id)
    if ncr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NCR not found")

    was_scrapped = ncr.disposition is Disposition.SCRAP
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ncr, field, value)

    if ncr.disposition is Disposition.SCRAP and not was_scrapped and ncr.lot_no:
        lot = db.scalar(
            select(StockLot).where(
                StockLot.item_id == ncr.item_id, StockLot.lot_no == ncr.lot_no, StockLot.qty > 0
            )
        )
        if lot:
            try:
                scrap_location = inv.default_location(db, LocationType.SCRAP)
                lot.status = LotStatus.AVAILABLE  # let the outbound leg consume it
                inv.post_movement(
                    db,
                    movement_type=MovementType.SCRAP,
                    item_id=ncr.item_id,
                    qty=min(ncr.qty, lot.qty),
                    lot_no=ncr.lot_no,
                    from_location_id=lot.location_id,
                    to_location_id=scrap_location.id,
                    ref_type="NCR",
                    ref_id=ncr.id,
                    ref_no=ncr.ncr_no,
                    user_id=user.id,
                    note=f"Scrapped under {ncr.ncr_no}",
                )
            except inv.StockError as exc:
                db.rollback()
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    if ncr.status is NcrStatus.CLOSED and ncr.closed_at is None:
        ncr.closed_at = datetime.now()

    db.commit()
    db.refresh(ncr)
    return ncr


@router.get("/defect-pareto")
def defect_pareto(days: int = 30, limit: int = 10, db: Session = Depends(get_db), _: User = AnyUser) -> list[dict]:
    """Which defects cost the most units - the QC improvement backlog, ranked."""
    from datetime import timedelta

    since = datetime.now() - timedelta(days=days)
    rows = db.execute(
        select(DefectCode.code, DefectCode.name, DefectCode.category, func.count(NonConformance.id), func.sum(NonConformance.qty))
        .join(NonConformance, NonConformance.defect_code_id == DefectCode.id)
        .where(NonConformance.created_at >= since)
        .group_by(DefectCode.id)
        .order_by(func.sum(NonConformance.qty).desc())
        .limit(limit)
    ).all()
    return [
        {"code": code, "name": name, "category": category, "count": count, "qty": float(qty or 0.0)}
        for code, name, category, count, qty in rows
    ]
