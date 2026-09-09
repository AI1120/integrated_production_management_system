"""Equipment master, downtime capture and the events OEE is calculated from."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base, EnumString, TimestampMixin
from ..enums import DowntimeCategory, MachineStatus, MaintenancePriority, MaintenanceStatus


class Machine(Base, TimestampMixin):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    work_center_id: Mapped[int] = mapped_column(ForeignKey("work_centers.id"), index=True)
    # Theoretical fastest time to produce one good unit - the P in OEE.
    ideal_cycle_seconds: Mapped[float] = mapped_column(Float, default=60.0)
    status: Mapped[MachineStatus] = mapped_column(EnumString(MachineStatus, 20), default=MachineStatus.IDLE)
    status_since: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # When a stopped machine is expected back. NULL while it is running, and
    # NULL on a stop nobody has estimated yet - which the scheduler reads as
    # "do not plan on this machine at all" rather than guessing a return.
    available_from: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    work_center: Mapped["WorkCenter"] = relationship(back_populates="machines")  # noqa: F821


class DowntimeReason(Base):
    __tablename__ = "downtime_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[DowntimeCategory] = mapped_column(EnumString(DowntimeCategory, 20), default=DowntimeCategory.UNPLANNED)
    # Planned stops (breaks, planned maintenance) are excluded from OEE loading time.
    affects_availability: Mapped[bool] = mapped_column(Boolean, default=True)


class DowntimeEvent(Base, TimestampMixin):
    """One stop on one machine. Open events have ended_at = NULL."""

    __tablename__ = "downtime_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    reason_id: Mapped[int] = mapped_column(ForeignKey("downtime_reasons.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    duration_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    reported_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    machine: Mapped["Machine"] = relationship()
    reason: Mapped["DowntimeReason"] = relationship()


class MaintenanceRequest(Base, TimestampMixin):
    __tablename__ = "maintenance_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[MaintenancePriority] = mapped_column(
        EnumString(MaintenancePriority, 10), default=MaintenancePriority.NORMAL
    )
    status: Mapped[MaintenanceStatus] = mapped_column(
        EnumString(MaintenanceStatus, 20), default=MaintenanceStatus.OPEN
    )
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    machine: Mapped["Machine"] = relationship()


class MaintenancePlan(Base, TimestampMixin):
    """Recurring preventive maintenance on one machine.

    A MaintenanceRequest is raised after something goes wrong. This is the other
    half: the stop you intend to take, so the scheduler stops loading work
    across a slot the machine was never going to be available for.
    """

    __tablename__ = "maintenance_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Calendar interval. Run-hours-based intervals are the obvious next step -
    # OEE already accumulates the run minutes they would need.
    interval_days: Mapped[int] = mapped_column(Integer, default=30)
    duration_minutes: Mapped[float] = mapped_column(Float, default=60.0)
    last_done_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    machine: Mapped["Machine"] = relationship()
