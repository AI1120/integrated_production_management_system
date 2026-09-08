from datetime import date, datetime

from pydantic import BaseModel, Field

from ..enums import LotStatus, MovementType
from .common import ORMModel
from .master import ItemRead, LocationRead


class StockLotRead(ORMModel):
    id: int
    item_id: int
    lot_no: str
    location_id: int
    qty: float
    status: LotStatus
    unit_cost: float
    received_at: datetime | None = None
    expiry_date: date | None = None
    source_order_id: int | None = None
    item: ItemRead
    location: LocationRead


class StockMovementRead(ORMModel):
    id: int
    movement_type: MovementType
    item_id: int
    lot_no: str | None = None
    from_location_id: int | None = None
    to_location_id: int | None = None
    qty: float
    unit_cost: float
    ref_type: str | None = None
    ref_id: int | None = None
    ref_no: str | None = None
    user_id: int | None = None
    occurred_at: datetime
    note: str | None = None
    item: ItemRead


class GoodsReceipt(BaseModel):
    item_id: int
    qty: float = Field(gt=0)
    lot_no: str | None = None
    location_id: int | None = None
    unit_cost: float = 0.0
    supplier_id: int | None = None
    expiry_date: date | None = None
    note: str | None = None


class StockTransfer(BaseModel):
    item_id: int
    lot_no: str
    from_location_id: int
    to_location_id: int
    qty: float = Field(gt=0)
    note: str | None = None


class StockAdjustment(BaseModel):
    item_id: int
    lot_no: str
    location_id: int
    qty: float = Field(description="Signed: positive adds stock, negative writes it down")
    reason: str


class StockOnHand(BaseModel):
    item_id: int
    item_code: str
    item_name: str
    uom: str
    on_hand: float
    safety_stock: float
    below_safety_stock: bool
    lot_count: int
    value: float
