"""Import every model so SQLAlchemy can resolve relationships and create_all sees them."""
from ..database import Base
from .counter import DocumentCounter
from .equipment import (
    DowntimeEvent,
    DowntimeReason,
    Machine,
    MaintenancePlan,
    MaintenanceRequest,
)
from .inventory import StockLot, StockMovement
from .master import Bom, BomLine, Item, Location, Partner, Routing, RoutingOperation, WorkCenter
from .production import Confirmation, OrderMaterial, OrderOperation, ProductionOrder
from .shift import Shift
from .quality import (
    DefectCode,
    Inspection,
    InspectionCharacteristic,
    InspectionPlan,
    InspectionResult,
    NonConformance,
)
from .user import User

__all__ = [
    "Base",
    "Bom",
    "BomLine",
    "Confirmation",
    "DefectCode",
    "DocumentCounter",
    "DowntimeEvent",
    "DowntimeReason",
    "Inspection",
    "InspectionCharacteristic",
    "InspectionPlan",
    "InspectionResult",
    "Item",
    "Location",
    "Machine",
    "MaintenancePlan",
    "MaintenanceRequest",
    "NonConformance",
    "OrderMaterial",
    "OrderOperation",
    "Partner",
    "ProductionOrder",
    "Routing",
    "RoutingOperation",
    "Shift",
    "StockLot",
    "StockMovement",
    "User",
    "WorkCenter",
]
