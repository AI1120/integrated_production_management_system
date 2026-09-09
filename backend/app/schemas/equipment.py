from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..enums import DowntimeCategory, MachineStatus
from .common import ORMModel, to_local_naive
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
    available_from: datetime | None = None
    work_center: WorkCenterRead


class MachineStatusUpdate(BaseModel):
    status: MachineStatus
    reason_id: int | None = None
    note: str | None = None
    # When the machine is expected back. Left out on a stop nobody can estimate,
    # and the scheduler then refuses to plan work onto it rather than guessing.
    available_from: datetime | None = None

    _local_times = field_validator("available_from")(to_local_naive)


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


class MaintenancePlanBase(BaseModel):
    machine_id: int
    name: str = Field(min_length=1, max_length=120)
    interval_days: int = Field(default=30, ge=1, le=3650)
    duration_minutes: float = Field(default=60.0, gt=0)
    is_active: bool = True


class MaintenancePlanCreate(MaintenancePlanBase):
    # Seeding a plan with its last service lets an existing machine come due on
    # its real schedule instead of one full interval from today.
    last_done_at: datetime | None = None

    _local_times = field_validator("last_done_at")(to_local_naive)


class MaintenancePlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    duration_minutes: float | None = Field(default=None, gt=0)
    is_active: bool | None = None


class MaintenancePlanRead(MaintenancePlanBase, ORMModel):
    id: int
    last_done_at: datetime | None = None
    next_due_at: datetime
    is_overdue: bool
    machine: MachineRead


class MaintenancePlanComplete(BaseModel):
    """Record a service as done, which is what moves the next due date."""

    done_at: datetime | None = None
    note: str | None = None

    _local_times = field_validator("done_at")(to_local_naive)


class MaintenanceDue(BaseModel):
    plan_id: int
    machine_id: int
    machine_code: str
    machine_name: str
    name: str
    interval_days: int
    duration_minutes: float
    last_done_at: datetime | None = None
    next_due_at: datetime
    days_until_due: float
    is_overdue: bool
