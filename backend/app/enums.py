"""Domain vocabularies shared by models, schemas and the UI."""
from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value


# --- Organisation -----------------------------------------------------------
class Role(StrEnum):
    ADMIN = "ADMIN"
    PLANNER = "PLANNER"
    OPERATOR = "OPERATOR"
    QC = "QC"
    WAREHOUSE = "WAREHOUSE"
    VIEWER = "VIEWER"


# --- Master data ------------------------------------------------------------
class ItemType(StrEnum):
    FINISHED_GOOD = "FINISHED_GOOD"
    SUB_ASSEMBLY = "SUB_ASSEMBLY"
    RAW_MATERIAL = "RAW_MATERIAL"
    CONSUMABLE = "CONSUMABLE"


class LocationType(StrEnum):
    RAW = "RAW"
    WIP = "WIP"
    FINISHED = "FINISHED"
    QUARANTINE = "QUARANTINE"
    SCRAP = "SCRAP"


# --- Production -------------------------------------------------------------
class OrderStatus(StrEnum):
    DRAFT = "DRAFT"
    RELEASED = "RELEASED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class OperationStatus(StrEnum):
    PENDING = "PENDING"
    SETUP = "SETUP"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


# --- Inventory --------------------------------------------------------------
class LotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    QUARANTINE = "QUARANTINE"
    REJECTED = "REJECTED"
    CONSUMED = "CONSUMED"


class MovementType(StrEnum):
    RECEIPT = "RECEIPT"                      # goods-in from supplier
    ISSUE = "ISSUE"                          # material issued to a work order
    PRODUCTION_RECEIPT = "PRODUCTION_RECEIPT"  # finished output booked into stock
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"
    SCRAP = "SCRAP"
    RETURN = "RETURN"                        # unused material returned from the floor


# --- Quality ----------------------------------------------------------------
class InspectionType(StrEnum):
    INCOMING = "INCOMING"
    IN_PROCESS = "IN_PROCESS"
    FINAL = "FINAL"


class Judgment(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


class CharacteristicType(StrEnum):
    NUMERIC = "NUMERIC"
    ATTRIBUTE = "ATTRIBUTE"


class Disposition(StrEnum):
    PENDING = "PENDING"
    REWORK = "REWORK"
    SCRAP = "SCRAP"
    USE_AS_IS = "USE_AS_IS"
    RETURN_TO_SUPPLIER = "RETURN_TO_SUPPLIER"


class NcrStatus(StrEnum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    CLOSED = "CLOSED"


# --- Equipment --------------------------------------------------------------
class MachineStatus(StrEnum):
    IDLE = "IDLE"
    SETUP = "SETUP"
    RUNNING = "RUNNING"
    DOWN = "DOWN"
    MAINTENANCE = "MAINTENANCE"


class DowntimeCategory(StrEnum):
    PLANNED = "PLANNED"
    UNPLANNED = "UNPLANNED"


class MaintenanceStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class MaintenancePriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
