"""Master data: items, bills of material, routings, work centres, locations."""
from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base, EnumString, TimestampMixin
from ..enums import ItemType, LocationType


class Item(Base, TimestampMixin):
    """Part master - everything that can be stocked, made or bought."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    item_type: Mapped[ItemType] = mapped_column(EnumString(ItemType, 20), default=ItemType.RAW_MATERIAL)
    uom: Mapped[str] = mapped_column(String(10), default="EA")
    standard_cost: Mapped[float] = mapped_column(Float, default=0.0)
    safety_stock: Mapped[float] = mapped_column(Float, default=0.0)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    is_lot_controlled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    boms: Mapped[list["Bom"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    routings: Mapped[list["Routing"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class Bom(Base, TimestampMixin):
    """Bill of material header. One active version per item at a time."""

    __tablename__ = "boms"
    __table_args__ = (UniqueConstraint("item_id", "version", name="uq_bom_item_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(20), default="A")
    description: Mapped[str | None] = mapped_column(String(200), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date | None] = mapped_column(Date, default=None)

    item: Mapped["Item"] = relationship(back_populates="boms")
    lines: Mapped[list["BomLine"]] = relationship(
        back_populates="bom", cascade="all, delete-orphan", order_by="BomLine.line_no"
    )


class BomLine(Base):
    __tablename__ = "bom_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, default=10)
    component_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    qty_per: Mapped[float] = mapped_column(Float, default=1.0)
    scrap_pct: Mapped[float] = mapped_column(Float, default=0.0)
    # Which routing step consumes this component (drives issue-to-operation).
    operation_seq: Mapped[int | None] = mapped_column(Integer, default=None)

    bom: Mapped["Bom"] = relationship(back_populates="lines")
    component: Mapped["Item"] = relationship()


class WorkCenter(Base, TimestampMixin):
    """A capacity group on the shop floor - a cell, a line, a bench."""

    __tablename__ = "work_centers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(255), default=None)
    capacity_per_hour: Mapped[float] = mapped_column(Float, default=1.0)
    cost_rate_per_hour: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    machines: Mapped[list["Machine"]] = relationship(back_populates="work_center")  # noqa: F821


class Routing(Base, TimestampMixin):
    """Process plan header - the ordered list of operations to build an item."""

    __tablename__ = "routings"
    __table_args__ = (UniqueConstraint("item_id", "version", name="uq_routing_item_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(20), default="A")
    description: Mapped[str | None] = mapped_column(String(200), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    item: Mapped["Item"] = relationship(back_populates="routings")
    operations: Mapped[list["RoutingOperation"]] = relationship(
        back_populates="routing", cascade="all, delete-orphan", order_by="RoutingOperation.seq"
    )


class RoutingOperation(Base):
    __tablename__ = "routing_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    routing_id: Mapped[int] = mapped_column(ForeignKey("routings.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=10)
    name: Mapped[str] = mapped_column(String(120))
    work_center_id: Mapped[int] = mapped_column(ForeignKey("work_centers.id"), index=True)
    setup_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    run_minutes_per_unit: Mapped[float] = mapped_column(Float, default=1.0)
    requires_inspection: Mapped[bool] = mapped_column(Boolean, default=False)
    instructions: Mapped[str | None] = mapped_column(Text, default=None)

    routing: Mapped["Routing"] = relationship(back_populates="operations")
    work_center: Mapped["WorkCenter"] = relationship()


class Location(Base, TimestampMixin):
    """Stock location. Flat for the sample plant; add a parent_id for multi-level racks."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    location_type: Mapped[LocationType] = mapped_column(EnumString(LocationType, 20), default=LocationType.RAW)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Partner(Base, TimestampMixin):
    """Customers and suppliers - minimal for the sample, extend for the full ERP link."""

    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_supplier: Mapped[bool] = mapped_column(Boolean, default=False)
    contact: Mapped[str | None] = mapped_column(String(160), default=None)
