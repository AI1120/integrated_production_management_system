from datetime import date

from pydantic import BaseModel, Field

from ..enums import ItemType, LocationType
from .common import ORMModel


# --- Item -------------------------------------------------------------------
class ItemBase(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    item_type: ItemType = ItemType.RAW_MATERIAL
    uom: str = "EA"
    standard_cost: float = 0.0
    safety_stock: float = 0.0
    lead_time_days: int = 0
    is_lot_controlled: bool = True
    is_active: bool = True


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    item_type: ItemType | None = None
    uom: str | None = None
    standard_cost: float | None = None
    safety_stock: float | None = None
    lead_time_days: int | None = None
    is_lot_controlled: bool | None = None
    is_active: bool | None = None


class ItemRead(ItemBase, ORMModel):
    id: int


class ItemWithStock(ItemRead):
    on_hand: float = 0.0
    below_safety_stock: bool = False


# --- BOM --------------------------------------------------------------------
class BomLineBase(BaseModel):
    line_no: int = 10
    component_id: int
    qty_per: float = 1.0
    scrap_pct: float = 0.0
    operation_seq: int | None = None


class BomLineRead(BomLineBase, ORMModel):
    id: int
    component: ItemRead


class BomBase(BaseModel):
    item_id: int
    version: str = "A"
    description: str | None = None
    is_active: bool = True
    effective_from: date | None = None


class BomCreate(BomBase):
    lines: list[BomLineBase] = []


class BomRead(BomBase, ORMModel):
    id: int
    item: ItemRead
    lines: list[BomLineRead] = []


# --- Work centre ------------------------------------------------------------
class WorkCenterBase(BaseModel):
    code: str
    name: str
    description: str | None = None
    capacity_per_hour: float = 1.0
    cost_rate_per_hour: float = 0.0
    is_active: bool = True


class WorkCenterCreate(WorkCenterBase):
    pass


class WorkCenterRead(WorkCenterBase, ORMModel):
    id: int


# --- Routing ----------------------------------------------------------------
class RoutingOperationBase(BaseModel):
    seq: int = 10
    name: str
    work_center_id: int
    setup_minutes: float = 0.0
    run_minutes_per_unit: float = 1.0
    requires_inspection: bool = False
    instructions: str | None = None


class RoutingOperationRead(RoutingOperationBase, ORMModel):
    id: int
    work_center: WorkCenterRead


class RoutingBase(BaseModel):
    item_id: int
    version: str = "A"
    description: str | None = None
    is_active: bool = True


class RoutingCreate(RoutingBase):
    operations: list[RoutingOperationBase] = []


class RoutingRead(RoutingBase, ORMModel):
    id: int
    item: ItemRead
    operations: list[RoutingOperationRead] = []


# --- Location & partner -----------------------------------------------------
class LocationBase(BaseModel):
    code: str
    name: str
    location_type: LocationType = LocationType.RAW
    is_active: bool = True


class LocationCreate(LocationBase):
    pass


class LocationRead(LocationBase, ORMModel):
    id: int


class PartnerBase(BaseModel):
    code: str
    name: str
    is_customer: bool = False
    is_supplier: bool = False
    contact: str | None = None


class PartnerCreate(PartnerBase):
    pass


class PartnerRead(PartnerBase, ORMModel):
    id: int
