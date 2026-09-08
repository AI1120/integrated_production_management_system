from datetime import datetime

from pydantic import BaseModel, Field

from ..enums import OperationStatus, OrderStatus
from .common import ORMModel
from .master import ItemRead, WorkCenterRead


class OrderMaterialRead(ORMModel):
    id: int
    line_no: int
    component_id: int
    operation_seq: int | None = None
    qty_required: float
    qty_issued: float
    qty_open: float
    component: ItemRead


class ConfirmationRead(ORMModel):
    id: int
    operation_id: int
    operator_id: int | None = None
    qty_good: float
    qty_scrap: float
    defect_code_id: int | None = None
    started_at: datetime
    ended_at: datetime
    duration_minutes: float
    note: str | None = None


class OrderOperationRead(ORMModel):
    id: int
    order_id: int
    seq: int
    name: str
    work_center_id: int
    machine_id: int | None = None
    setup_minutes: float
    run_minutes_per_unit: float
    requires_inspection: bool
    instructions: str | None = None
    status: OperationStatus
    qty_completed: float
    qty_scrapped: float
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    work_center: WorkCenterRead


class ProductionOrderCreate(BaseModel):
    item_id: int
    qty_ordered: float = Field(gt=0)
    bom_id: int | None = None
    routing_id: int | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    due_date: datetime | None = None
    priority: int = 5
    customer_id: int | None = None
    sales_ref: str | None = None
    note: str | None = None


class ProductionOrderRead(ORMModel):
    id: int
    order_no: str
    item_id: int
    bom_id: int | None = None
    routing_id: int | None = None
    qty_ordered: float
    qty_produced: float
    qty_scrapped: float
    qty_remaining: float
    status: OrderStatus
    priority: int
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    due_date: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    output_lot_no: str | None = None
    sales_ref: str | None = None
    note: str | None = None
    created_at: datetime
    item: ItemRead


class ProductionOrderDetail(ProductionOrderRead):
    operations: list[OrderOperationRead] = []
    materials: list[OrderMaterialRead] = []


class ConfirmationCreate(BaseModel):
    """What the operator terminal posts when a batch comes off the station."""

    operation_id: int
    qty_good: float = Field(ge=0, default=0)
    qty_scrap: float = Field(ge=0, default=0)
    defect_code_id: int | None = None
    machine_id: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    note: str | None = None


class MaterialIssue(BaseModel):
    material_id: int
    qty: float = Field(gt=0)
    lot_no: str | None = None
    from_location_id: int | None = None


class ScanLookup(BaseModel):
    """A single barcode/QR payload from the shop-floor scanner."""

    code: str = Field(min_length=1)


class ScanResult(BaseModel):
    kind: str  # ORDER | ITEM | LOT | BADGE | UNKNOWN
    label: str
    id: int | None = None
    payload: dict = {}
