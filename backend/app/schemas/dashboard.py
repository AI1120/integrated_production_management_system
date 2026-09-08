from datetime import datetime

from pydantic import BaseModel


class KpiCard(BaseModel):
    key: str
    label: str
    value: float
    unit: str = ""
    hint: str | None = None


class TrendPoint(BaseModel):
    label: str
    good: float = 0.0
    scrap: float = 0.0
    target: float = 0.0


class StatusSlice(BaseModel):
    label: str
    value: float


class DashboardRead(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    kpis: list[KpiCard]
    production_trend: list[TrendPoint]
    order_status: list[StatusSlice]
    machine_status: list[StatusSlice]
    downtime_pareto: list[dict]
    top_defects: list[dict]
    low_stock: list[dict]
    plant_oee: dict
