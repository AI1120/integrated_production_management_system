from datetime import datetime

from pydantic import BaseModel, Field

from ..enums import DowntimeCategory, MachineStatus
from .common import ORMModel
from .master import WorkCenterRead


class MachineBase(BaseModel):
    code: str
    name: str
    work_center_id: int
    ideal_cycle_seconds: float = 60.0
    is_active: bool = True


class MachineCreate(MachineBase):
    pass


class MachineRead(MachineBase, ORMModel):
    id: int
    status: MachineStatus
    status_since: datetime | None = None
    work_center: WorkCenterRead


class MachineStatusUpdate(BaseModel):
    status: MachineStatus
    reason_id: int | None = None
    note: str | None = None


class DowntimeReasonBase(BaseModel):
    code: str
    name: str
    category: DowntimeCategory = DowntimeCategory.UNPLANNED
    affects_availability: bool = True


class DowntimeReasonCreate(DowntimeReasonBase):
    pass


class DowntimeReasonRead(DowntimeReasonBase, ORMModel):
    id: int


class DowntimeStart(BaseModel):
    machine_id: int
    reason_id: int
    started_at: datetime | None = None
    note: str | None = None


class DowntimeEnd(BaseModel):
    ended_at: datetime | None = None
    note: str | None = None


class DowntimeEventRead(ORMModel):
    id: int
    machine_id: int
    reason_id: int
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: float
    note: str | None = None
    machine: MachineRead
    reason: DowntimeReasonRead


class MaintenanceRequestCreate(BaseModel):
    machine_id: int
    title: str = Field(min_length=1)
    description: str | None = None
    priority: str = "NORMAL"


class MaintenanceRequestRead(ORMModel):
    id: int
    request_no: str
    machine_id: int
    title: str
    description: str | None = None
    priority: str
    status: str
    closed_at: datetime | None = None
    created_at: datetime
    machine: MachineRead


class OeeRead(BaseModel):
    machine_id: int
    machine_code: str
    machine_name: str
    window_start: datetime
    window_end: datetime
    scheduled_minutes: float
    planned_downtime_minutes: float
    unplanned_downtime_minutes: float
    loading_minutes: float
    run_minutes: float
    good_count: float
    scrap_count: float
    total_count: float
    availability: float
    performance: float
    quality: float
    oee: float
