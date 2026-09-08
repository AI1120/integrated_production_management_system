"""Stock lots and the immutable movement ledger behind every quantity change."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base, EnumString, TimestampMixin
from ..enums import LotStatus, MovementType


class StockLot(Base, TimestampMixin):
    """On-hand quantity of one item, in one lot, at one location."""

    __tablename__ = "stock_lots"
    __table_args__ = (UniqueConstraint("item_id", "lot_no", "location_id", name="uq_lot_item_no_loc"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    lot_no: Mapped[str] = mapped_column(String(40), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[LotStatus] = mapped_column(EnumString(LotStatus, 20), default=LotStatus.AVAILABLE, index=True)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    expiry_date: Mapped[date | None] = mapped_column(Date, default=None)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), default=None)
    # Traceability: which work order produced this lot.
    source_order_id: Mapped[int | None] = mapped_column(ForeignKey("production_orders.id"), default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    location: Mapped["Location"] = relationship()  # noqa: F821


class StockMovement(Base):
    """Append-only ledger. Never updated - corrections are new opposing movements."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    movement_type: Mapped[MovementType] = mapped_column(EnumString(MovementType, 30), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    lot_no: Mapped[str | None] = mapped_column(String(40), index=True, default=None)
    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), default=None)
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), default=None)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)

    # Loose back-reference to whatever caused the movement (order, inspection, NCR...).
    ref_type: Mapped[str | None] = mapped_column(String(40), default=None)
    ref_id: Mapped[int | None] = mapped_column(default=None)
    ref_no: Mapped[str | None] = mapped_column(String(40), default=None)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
