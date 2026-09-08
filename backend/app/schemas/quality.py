from datetime import datetime

from pydantic import BaseModel, Field

from ..enums import CharacteristicType, Disposition, InspectionType, Judgment, NcrStatus
from .common import ORMModel
from .master import ItemRead


class DefectCodeBase(BaseModel):
    code: str
    name: str
    category: str = "GENERAL"
    is_active: bool = True


class DefectCodeCreate(DefectCodeBase):
    pass


class DefectCodeRead(DefectCodeBase, ORMModel):
    id: int


class CharacteristicBase(BaseModel):
    seq: int = 10
    name: str
    char_type: CharacteristicType = CharacteristicType.NUMERIC
    uom: str | None = None
    target: float | None = None
    lower_limit: float | None = None
    upper_limit: float | None = None
    method: str | None = None


class CharacteristicRead(CharacteristicBase, ORMModel):
    id: int
    plan_id: int


class InspectionPlanBase(BaseModel):
    code: str
    name: str
    item_id: int | None = None
    inspection_type: InspectionType = InspectionType.FINAL
    operation_seq: int | None = None
    sample_size: int = 5
    is_active: bool = True


class InspectionPlanCreate(InspectionPlanBase):
    characteristics: list[CharacteristicBase] = []


class InspectionPlanRead(InspectionPlanBase, ORMModel):
    id: int
    characteristics: list[CharacteristicRead] = []


class InspectionResultIn(BaseModel):
    characteristic_id: int | None = None
    characteristic_name: str | None = None
    sample_no: int = 1
    value_numeric: float | None = None
    value_text: str | None = None


class InspectionResultRead(ORMModel):
    id: int
    characteristic_id: int | None = None
    characteristic_name: str
    sample_no: int
    value_numeric: float | None = None
    value_text: str | None = None
    judgment: Judgment


class InspectionCreate(BaseModel):
    item_id: int
    inspection_type: InspectionType = InspectionType.FINAL
    plan_id: int | None = None
    lot_no: str | None = None
    order_id: int | None = None
    operation_id: int | None = None
    qty_inspected: float = Field(gt=0)
    qty_rejected: float = 0.0
    results: list[InspectionResultIn] = []
    note: str | None = None
    # Move the inspected lot out of quarantine automatically when it passes.
    release_lot: bool = True


class InspectionRead(ORMModel):
    id: int
    inspection_no: str
    plan_id: int | None = None
    inspection_type: InspectionType
    item_id: int
    lot_no: str | None = None
    order_id: int | None = None
    operation_id: int | None = None
    qty_inspected: float
    qty_accepted: float
    qty_rejected: float
    result: Judgment
    inspector_id: int | None = None
    inspected_at: datetime
    note: str | None = None
    item: ItemRead
    results: list[InspectionResultRead] = []


class NcrCreate(BaseModel):
    item_id: int
    qty: float = Field(gt=0)
    lot_no: str | None = None
    order_id: int | None = None
    inspection_id: int | None = None
    defect_code_id: int | None = None
    description: str | None = None


class NcrUpdate(BaseModel):
    disposition: Disposition | None = None
    status: NcrStatus | None = None
    root_cause: str | None = None
    corrective_action: str | None = None


class NcrRead(ORMModel):
    id: int
    ncr_no: str
    item_id: int
    lot_no: str | None = None
    order_id: int | None = None
    inspection_id: int | None = None
    defect_code_id: int | None = None
    qty: float
    description: str | None = None
    disposition: Disposition
    status: NcrStatus
    root_cause: str | None = None
    corrective_action: str | None = None
    closed_at: datetime | None = None
    created_at: datetime
    item: ItemRead
    defect_code: DefectCodeRead | None = None
