from datetime import datetime

from pydantic import BaseModel


class ScheduledOperationRead(BaseModel):
    order_id: int
    order_no: str
    item_code: str
    operation_id: int
    seq: int
    name: str
    work_center_id: int
    work_center_code: str
    machine_id: int
    machine_code: str
    qty: float
    setup_minutes: float
    run_minutes: float
    start: datetime
    end: datetime
    offset_minutes: float
    work_minutes: float


class ScheduledOrderRead(BaseModel):
    order_id: int
    order_no: str
    item_code: str
    item_name: str
    qty: float
    priority: int
    due: datetime | None = None
    start: datetime
    end: datetime
    lateness_hours: float
    operations: list[ScheduledOperationRead] = []


class UtilisationRow(BaseModel):
    work_center_id: int
    work_center_code: str
    work_center_name: str
    machines: int
    loaded_hours: float
    capacity_hours: float
    setup_hours: float
    utilisation: float


class ScheduleRead(BaseModel):
    rule: str
    horizon_start: datetime
    horizon_end: datetime
    orders: list[ScheduledOrderRead]
    operations: list[ScheduledOperationRead]
    unscheduled: list[dict]
    day_marks: list[dict]
    makespan_hours: float
    total_lateness_hours: float
    max_lateness_hours: float
    late_orders: int
    utilisation: list[UtilisationRow]


class RuleResult(BaseModel):
    rule: str
    description: str
    makespan_hours: float
    total_lateness_hours: float
    max_lateness_hours: float
    late_orders: int
    scheduled_orders: int
    unscheduled_orders: int


class ComparisonRead(BaseModel):
    objective: str
    objective_label: str
    results: list[RuleResult]
    best_rule: str
    baseline_rule: str
    improvement: float
    improvement_pct: float


class BottleneckRead(UtilisationRow):
    is_constraint: bool
    idle_capacity_elsewhere_hours: float
    setup_share: float


class FlowRead(BaseModel):
    orders: int
    work_hours: float
    flow_hours: float
    queue_hours: float
    efficiency: float


class Recommendation(BaseModel):
    area: str
    severity: str
    title: str
    detail: str
    action: str
    value: str


class OrderCostRead(BaseModel):
    order_id: int
    order_no: str
    item_code: str
    item_name: str
    status: str
    qty_ordered: float
    qty_produced: float
    qty_scrapped: float
    standard_material: float
    standard_labour: float
    standard_total: float
    actual_material: float
    actual_labour: float
    actual_total: float
    material_variance: float
    labour_variance: float
    total_variance: float
    scrap_cost: float
    unit_cost_standard: float
    unit_cost_actual: float


class CostSummaryRead(BaseModel):
    orders: int
    standard_total: float
    actual_total: float
    total_variance: float
    material_variance: float
    labour_variance: float
    scrap_cost: float
    variance_pct: float
    worst_orders: list[OrderCostRead] = []


class OptimizationReport(BaseModel):
    generated_at: datetime
    schedule: ScheduleRead
    comparison: ComparisonRead
    bottleneck: BottleneckRead | None = None
    flow: FlowRead
    setups: list[dict]
    cost: CostSummaryRead
    scrap_cost: list[dict]
    recommendations: list[Recommendation]


class ApplyScheduleRequest(BaseModel):
    rule: str = "PRIORITY"
    horizon_days: int = 30
