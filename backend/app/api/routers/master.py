"""Master data endpoints: items, BOMs, routings, work centres, locations, partners."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...enums import ItemType, Role
from ...models.master import (
    Bom,
    BomLine,
    Item,
    Location,
    Partner,
    Routing,
    RoutingOperation,
    WorkCenter,
)
from ...models.user import User
from ...schemas.master import (
    BomCreate,
    BomRead,
    ItemCreate,
    ItemRead,
    ItemUpdate,
    ItemWithStock,
    LocationCreate,
    LocationRead,
    PartnerCreate,
    PartnerRead,
    RoutingCreate,
    RoutingRead,
    WorkCenterCreate,
    WorkCenterRead,
)
from ...services import inventory_service as inv
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/master", tags=["master data"])

Planner = Depends(require_roles(Role.PLANNER))
AnyUser = Depends(get_current_user)


# --- Items ------------------------------------------------------------------
@router.get("/items", response_model=list[ItemWithStock])
def list_items(
    q: str | None = None,
    item_type: ItemType | None = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[ItemWithStock]:
    stmt = select(Item)
    if active_only:
        stmt = stmt.where(Item.is_active.is_(True))
    if item_type:
        stmt = stmt.where(Item.item_type == item_type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Item.code.ilike(like), Item.name.ilike(like)))

    result = []
    for item in db.scalars(stmt.order_by(Item.code)):
        qty = inv.on_hand(db, item.id)
        result.append(
            ItemWithStock(
                **ItemRead.model_validate(item).model_dump(),
                on_hand=qty,
                below_safety_stock=qty < item.safety_stock,
            )
        )
    return result


@router.get("/items/{item_id}", response_model=ItemWithStock)
def get_item(item_id: int, db: Session = Depends(get_db), _: User = AnyUser) -> ItemWithStock:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    qty = inv.on_hand(db, item.id)
    return ItemWithStock(
        **ItemRead.model_validate(item).model_dump(),
        on_hand=qty,
        below_safety_stock=qty < item.safety_stock,
    )


@router.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_db), _: User = Planner) -> Item:
    if db.scalar(select(Item).where(Item.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Item code {payload.code} already exists")
    item = Item(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(
    item_id: int, payload: ItemUpdate, db: Session = Depends(get_db), _: User = Planner
) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


# --- Bills of material ------------------------------------------------------
@router.get("/boms", response_model=list[BomRead])
def list_boms(
    item_id: int | None = None, db: Session = Depends(get_db), _: User = AnyUser
) -> list[Bom]:
    stmt = select(Bom).options(selectinload(Bom.lines).selectinload(BomLine.component), selectinload(Bom.item))
    if item_id:
        stmt = stmt.where(Bom.item_id == item_id)
    return list(db.scalars(stmt.order_by(Bom.id.desc())))


@router.get("/boms/{bom_id}", response_model=BomRead)
def get_bom(bom_id: int, db: Session = Depends(get_db), _: User = AnyUser) -> Bom:
    bom = db.get(Bom, bom_id)
    if bom is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BOM not found")
    return bom


@router.post("/boms", response_model=BomRead, status_code=status.HTTP_201_CREATED)
def create_bom(payload: BomCreate, db: Session = Depends(get_db), _: User = Planner) -> Bom:
    if db.get(Item, payload.item_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parent item not found")
    if db.scalar(select(Bom).where(Bom.item_id == payload.item_id, Bom.version == payload.version)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Version {payload.version} already exists for this item")

    bom = Bom(**payload.model_dump(exclude={"lines"}))
    db.add(bom)
    db.flush()
    for line in payload.lines:
        if line.component_id == payload.item_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "An item cannot be a component of itself")
        db.add(BomLine(bom_id=bom.id, **line.model_dump()))

    # Only one active BOM per item.
    if bom.is_active:
        for other in db.scalars(select(Bom).where(Bom.item_id == bom.item_id, Bom.id != bom.id)):
            other.is_active = False

    db.commit()
    db.refresh(bom)
    return bom


@router.delete("/boms/{bom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bom(bom_id: int, db: Session = Depends(get_db), _: User = Planner) -> None:
    bom = db.get(Bom, bom_id)
    if bom is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BOM not found")
    db.delete(bom)
    db.commit()


# --- Routings ---------------------------------------------------------------
@router.get("/routings", response_model=list[RoutingRead])
def list_routings(
    item_id: int | None = None, db: Session = Depends(get_db), _: User = AnyUser
) -> list[Routing]:
    stmt = select(Routing).options(
        selectinload(Routing.operations).selectinload(RoutingOperation.work_center),
        selectinload(Routing.item),
    )
    if item_id:
        stmt = stmt.where(Routing.item_id == item_id)
    return list(db.scalars(stmt.order_by(Routing.id.desc())))


@router.post("/routings", response_model=RoutingRead, status_code=status.HTTP_201_CREATED)
def create_routing(payload: RoutingCreate, db: Session = Depends(get_db), _: User = Planner) -> Routing:
    if db.get(Item, payload.item_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    if db.scalar(select(Routing).where(Routing.item_id == payload.item_id, Routing.version == payload.version)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Version {payload.version} already exists for this item")
    if not payload.operations:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A routing needs at least one operation")

    routing = Routing(**payload.model_dump(exclude={"operations"}))
    db.add(routing)
    db.flush()
    for op in payload.operations:
        if db.get(WorkCenter, op.work_center_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Work centre {op.work_center_id} not found")
        db.add(RoutingOperation(routing_id=routing.id, **op.model_dump()))

    if routing.is_active:
        for other in db.scalars(select(Routing).where(Routing.item_id == routing.item_id, Routing.id != routing.id)):
            other.is_active = False

    db.commit()
    db.refresh(routing)
    return routing


@router.delete("/routings/{routing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routing(routing_id: int, db: Session = Depends(get_db), _: User = Planner) -> None:
    routing = db.get(Routing, routing_id)
    if routing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Routing not found")
    db.delete(routing)
    db.commit()


# --- Work centres, locations, partners --------------------------------------
@router.get("/work-centers", response_model=list[WorkCenterRead])
def list_work_centers(db: Session = Depends(get_db), _: User = AnyUser) -> list[WorkCenter]:
    return list(db.scalars(select(WorkCenter).order_by(WorkCenter.code)))


@router.post("/work-centers", response_model=WorkCenterRead, status_code=status.HTTP_201_CREATED)
def create_work_center(
    payload: WorkCenterCreate, db: Session = Depends(get_db), _: User = Planner
) -> WorkCenter:
    if db.scalar(select(WorkCenter).where(WorkCenter.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Work centre {payload.code} already exists")
    wc = WorkCenter(**payload.model_dump())
    db.add(wc)
    db.commit()
    db.refresh(wc)
    return wc


@router.get("/locations", response_model=list[LocationRead])
def list_locations(db: Session = Depends(get_db), _: User = AnyUser) -> list[Location]:
    return list(db.scalars(select(Location).order_by(Location.code)))


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationCreate, db: Session = Depends(get_db), _: User = Planner) -> Location:
    if db.scalar(select(Location).where(Location.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Location {payload.code} already exists")
    location = Location(**payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/partners", response_model=list[PartnerRead])
def list_partners(
    role: str | None = Query(default=None, pattern="^(customer|supplier)$"),
    db: Session = Depends(get_db),
    _: User = AnyUser,
) -> list[Partner]:
    stmt = select(Partner)
    if role == "customer":
        stmt = stmt.where(Partner.is_customer.is_(True))
    elif role == "supplier":
        stmt = stmt.where(Partner.is_supplier.is_(True))
    return list(db.scalars(stmt.order_by(Partner.code)))


@router.post("/partners", response_model=PartnerRead, status_code=status.HTTP_201_CREATED)
def create_partner(payload: PartnerCreate, db: Session = Depends(get_db), _: User = Planner) -> Partner:
    if db.scalar(select(Partner).where(Partner.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Partner {payload.code} already exists")
    partner = Partner(**payload.model_dump())
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner
