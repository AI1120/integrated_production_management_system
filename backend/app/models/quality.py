"""Inspection plans, recorded inspections and non-conformance handling."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base, EnumString, TimestampMixin
from ..enums import CharacteristicType, Disposition, InspectionType, Judgment, NcrStatus


class DefectCode(Base):
    __tablename__ = "defect_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40), default="GENERAL")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InspectionPlan(Base, TimestampMixin):
    """What to check, for which item, at which stage."""

    __tablename__ = "inspection_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), default=None, index=True)
    inspection_type: Mapped[InspectionType] = mapped_column(EnumString(InspectionType, 20), default=InspectionType.FINAL)
    # Applies to this routing step only; NULL means any step.
    operation_seq: Mapped[int | None] = mapped_column(Integer, default=None)
    sample_size: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    item: Mapped["Item"] = relationship()  # noqa: F821
    characteristics: Mapped[list["InspectionCharacteristic"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="InspectionCharacteristic.seq"
    )


class InspectionCharacteristic(Base):
    """One measurable or observable property on a plan."""

    __tablename__ = "inspection_characteristics"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("inspection_plans.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=10)
    name: Mapped[str] = mapped_column(String(120))
    char_type: Mapped[CharacteristicType] = mapped_column(EnumString(CharacteristicType, 20), default=CharacteristicType.NUMERIC)
    uom: Mapped[str | None] = mapped_column(String(20), default=None)
    target: Mapped[float | None] = mapped_column(Float, default=None)
    lower_limit: Mapped[float | None] = mapped_column(Float, default=None)
    upper_limit: Mapped[float | None] = mapped_column(Float, default=None)
    method: Mapped[str | None] = mapped_column(String(160), default=None)

    plan: Mapped["InspectionPlan"] = relationship(back_populates="characteristics")


class Inspection(Base, TimestampMixin):
    """A recorded inspection event against a lot, an order or an operation."""

    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_plans.id"), default=None)
    inspection_type: Mapped[InspectionType] = mapped_column(EnumString(InspectionType, 20), default=InspectionType.FINAL)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    lot_no: Mapped[str | None] = mapped_column(String(40), index=True, default=None)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("production_orders.id"), default=None, index=True)
    operation_id: Mapped[int | None] = mapped_column(ForeignKey("order_operations.id"), default=None)

    qty_inspected: Mapped[float] = mapped_column(Float, default=0.0)
    qty_accepted: Mapped[float] = mapped_column(Float, default=0.0)
    qty_rejected: Mapped[float] = mapped_column(Float, default=0.0)
    result: Mapped[Judgment] = mapped_column(EnumString(Judgment, 20), default=Judgment.PENDING, index=True)

    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    inspected_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    plan: Mapped["InspectionPlan"] = relationship()
    results: Mapped[list["InspectionResult"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )


class InspectionResult(Base):
    """One measured sample value, judged against the characteristic limits."""

    __tablename__ = "inspection_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    characteristic_id: Mapped[int | None] = mapped_column(
        ForeignKey("inspection_characteristics.id"), default=None
    )
    characteristic_name: Mapped[str] = mapped_column(String(120))
    sample_no: Mapped[int] = mapped_column(Integer, default=1)
    value_numeric: Mapped[float | None] = mapped_column(Float, default=None)
    value_text: Mapped[str | None] = mapped_column(String(160), default=None)
    judgment: Mapped[Judgment] = mapped_column(EnumString(Judgment, 20), default=Judgment.PENDING)

    inspection: Mapped["Inspection"] = relationship(back_populates="results")


class NonConformance(Base, TimestampMixin):
    """NCR - raised when material fails, tracked through to a disposition."""

    __tablename__ = "non_conformances"

    id: Mapped[int] = mapped_column(primary_key=True)
    ncr_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    lot_no: Mapped[str | None] = mapped_column(String(40), default=None)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("production_orders.id"), default=None)
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspections.id"), default=None)
    defect_code_id: Mapped[int | None] = mapped_column(ForeignKey("defect_codes.id"), default=None)

    qty: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    disposition: Mapped[Disposition] = mapped_column(EnumString(Disposition, 30), default=Disposition.PENDING)
    status: Mapped[NcrStatus] = mapped_column(EnumString(NcrStatus, 20), default=NcrStatus.OPEN, index=True)
    root_cause: Mapped[str | None] = mapped_column(Text, default=None)
    corrective_action: Mapped[str | None] = mapped_column(Text, default=None)

    raised_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    defect_code: Mapped["DefectCode"] = relationship()
