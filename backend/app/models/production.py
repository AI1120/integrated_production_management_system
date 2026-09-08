"""Production orders, their operations, and shop-floor confirmations."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base, EnumString, TimestampMixin
from ..enums import OperationStatus, OrderStatus


class ProductionOrder(Base, TimestampMixin):
    """A work order: build N of an item, using a frozen copy of a BOM and routing."""

    __tablename__ = "production_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    bom_id: Mapped[int | None] = mapped_column(ForeignKey("boms.id"), default=None)
    routing_id: Mapped[int | None] = mapped_column(ForeignKey("routings.id"), default=None)

    qty_ordered: Mapped[float] = mapped_column(Float, default=0.0)
    qty_produced: Mapped[float] = mapped_column(Float, default=0.0)
    qty_scrapped: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[OrderStatus] = mapped_column(EnumString(OrderStatus, 20), default=OrderStatus.DRAFT, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)

    # The commitment to the customer. Set once, never rewritten by scheduling -
    # otherwise applying a schedule makes the due date equal the plan, lateness
    # collapses to zero and the whole analysis becomes self-referential.
    due_date: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # The current plan. This is what the scheduler owns and overwrites.
    planned_start: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    planned_end: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    customer_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), default=None)
    sales_ref: Mapped[str | None] = mapped_column(String(60), default=None)
    output_lot_no: Mapped[str | None] = mapped_column(String(40), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    operations: Mapped[list["OrderOperation"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderOperation.seq"
    )
    materials: Mapped[list["OrderMaterial"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderMaterial.line_no"
    )

    @property
    def qty_remaining(self) -> float:
        return max(self.qty_ordered - self.qty_produced, 0.0)


class OrderOperation(Base, TimestampMixin):
    """A routing step copied onto the order, so master-data edits never rewrite history."""

    __tablename__ = "order_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=10)
    name: Mapped[str] = mapped_column(String(120))
    work_center_id: Mapped[int] = mapped_column(ForeignKey("work_centers.id"), index=True)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), default=None, index=True)

    setup_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    run_minutes_per_unit: Mapped[float] = mapped_column(Float, default=1.0)
    requires_inspection: Mapped[bool] = mapped_column(default=False)
    instructions: Mapped[str | None] = mapped_column(Text, default=None)

    status: Mapped[OperationStatus] = mapped_column(EnumString(OperationStatus, 20), default=OperationStatus.PENDING, index=True)
    qty_completed: Mapped[float] = mapped_column(Float, default=0.0)
    qty_scrapped: Mapped[float] = mapped_column(Float, default=0.0)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    order: Mapped["ProductionOrder"] = relationship(back_populates="operations")
    work_center: Mapped["WorkCenter"] = relationship()  # noqa: F821
    machine: Mapped["Machine"] = relationship()  # noqa: F821
    confirmations: Mapped[list["Confirmation"]] = relationship(
        back_populates="operation", cascade="all, delete-orphan"
    )


class OrderMaterial(Base):
    """Exploded BOM for the order: what must be issued, and what actually was."""

    __tablename__ = "order_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, default=10)
    component_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    operation_seq: Mapped[int | None] = mapped_column(Integer, default=None)
    qty_required: Mapped[float] = mapped_column(Float, default=0.0)
    qty_issued: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped["ProductionOrder"] = relationship(back_populates="materials")
    component: Mapped["Item"] = relationship()  # noqa: F821

    @property
    def qty_open(self) -> float:
        return max(self.qty_required - self.qty_issued, 0.0)


class Confirmation(Base, TimestampMixin):
    """One production report from the floor: good qty, scrap qty, time spent."""

    __tablename__ = "confirmations"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("order_operations.id", ondelete="CASCADE"), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    qty_good: Mapped[float] = mapped_column(Float, default=0.0)
    qty_scrap: Mapped[float] = mapped_column(Float, default=0.0)
    defect_code_id: Mapped[int | None] = mapped_column(ForeignKey("defect_codes.id"), default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    operation: Mapped["OrderOperation"] = relationship(back_populates="confirmations")
    operator: Mapped["User"] = relationship()  # noqa: F821
