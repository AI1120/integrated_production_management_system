/** Mirrors the Pydantic schemas served by the FastAPI backend. */

export type Role = 'ADMIN' | 'PLANNER' | 'OPERATOR' | 'QC' | 'WAREHOUSE' | 'VIEWER'
export type ItemType = 'FINISHED_GOOD' | 'SUB_ASSEMBLY' | 'RAW_MATERIAL' | 'CONSUMABLE'
export type LocationType = 'RAW' | 'WIP' | 'FINISHED' | 'QUARANTINE' | 'SCRAP'
export type OrderStatus = 'DRAFT' | 'RELEASED' | 'IN_PROGRESS' | 'COMPLETED' | 'CLOSED' | 'CANCELLED'
export type OperationStatus = 'PENDING' | 'SETUP' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'SKIPPED'
export type LotStatus = 'AVAILABLE' | 'QUARANTINE' | 'REJECTED' | 'CONSUMED'
export type MovementType =
  | 'RECEIPT' | 'ISSUE' | 'PRODUCTION_RECEIPT' | 'TRANSFER' | 'ADJUSTMENT' | 'SCRAP' | 'RETURN'
export type Judgment = 'PASS' | 'FAIL' | 'PENDING'
export type InspectionType = 'INCOMING' | 'IN_PROCESS' | 'FINAL'
export type Disposition = 'PENDING' | 'REWORK' | 'SCRAP' | 'USE_AS_IS' | 'RETURN_TO_SUPPLIER'
export type NcrStatus = 'OPEN' | 'IN_REVIEW' | 'CLOSED'
export type MachineStatus = 'IDLE' | 'SETUP' | 'RUNNING' | 'DOWN' | 'MAINTENANCE'

export interface User {
  id: number
  username: string
  full_name: string
  badge_no: string | null
  role: Role
  is_active: boolean
}

export interface Item {
  id: number
  code: string
  name: string
  description: string | null
  item_type: ItemType
  uom: string
  standard_cost: number
  safety_stock: number
  lead_time_days: number
  is_lot_controlled: boolean
  is_active: boolean
  on_hand?: number
  below_safety_stock?: boolean
}

export interface WorkCenter {
  id: number
  code: string
  name: string
  description: string | null
  capacity_per_hour: number
  cost_rate_per_hour: number
  is_active: boolean
}

export interface Location {
  id: number
  code: string
  name: string
  location_type: LocationType
  is_active: boolean
}

export interface BomLine {
  id: number
  line_no: number
  component_id: number
  qty_per: number
  scrap_pct: number
  operation_seq: number | null
  component: Item
}

export interface Bom {
  id: number
  item_id: number
  version: string
  description: string | null
  is_active: boolean
  item: Item
  lines: BomLine[]
}

export interface RoutingOperation {
  id: number
  seq: number
  name: string
  work_center_id: number
  setup_minutes: number
  run_minutes_per_unit: number
  requires_inspection: boolean
  instructions: string | null
  work_center: WorkCenter
}

export interface Routing {
  id: number
  item_id: number
  version: string
  description: string | null
  is_active: boolean
  item: Item
  operations: RoutingOperation[]
}

export interface OrderOperation {
  id: number
  order_id: number
  seq: number
  name: string
  work_center_id: number
  machine_id: number | null
  setup_minutes: number
  run_minutes_per_unit: number
  requires_inspection: boolean
  instructions: string | null
  status: OperationStatus
  qty_completed: number
  qty_scrapped: number
  actual_start: string | null
  actual_end: string | null
  work_center: WorkCenter
}

export interface OrderMaterial {
  id: number
  line_no: number
  component_id: number
  operation_seq: number | null
  qty_required: number
  qty_issued: number
  qty_open: number
  component: Item
}

export interface ProductionOrder {
  id: number
  order_no: string
  item_id: number
  bom_id: number | null
  routing_id: number | null
  qty_ordered: number
  qty_produced: number
  qty_scrapped: number
  qty_remaining: number
  status: OrderStatus
  priority: number
  planned_start: string | null
  planned_end: string | null
  due_date: string | null
  actual_start: string | null
  actual_end: string | null
  output_lot_no: string | null
  sales_ref: string | null
  note: string | null
  created_at: string
  item: Item
  operations?: OrderOperation[]
  materials?: OrderMaterial[]
}

export interface Confirmation {
  id: number
  operation_id: number
  operator_id: number | null
  qty_good: number
  qty_scrap: number
  defect_code_id: number | null
  started_at: string
  ended_at: string
  duration_minutes: number
  note: string | null
}

export interface StockLot {
  id: number
  item_id: number
  lot_no: string
  location_id: number
  qty: number
  status: LotStatus
  unit_cost: number
  received_at: string | null
  expiry_date: string | null
  source_order_id: number | null
  item: Item
  location: Location
}

export interface StockMovement {
  id: number
  movement_type: MovementType
  item_id: number
  lot_no: string | null
  from_location_id: number | null
  to_location_id: number | null
  qty: number
  unit_cost: number
  ref_type: string | null
  ref_id: number | null
  ref_no: string | null
  occurred_at: string
  note: string | null
  item: Item
}

export interface StockOnHand {
  item_id: number
  item_code: string
  item_name: string
  uom: string
  on_hand: number
  safety_stock: number
  below_safety_stock: boolean
  lot_count: number
  value: number
}

export interface LotTrace {
  lot_no: string
  source_order_id: number | null
  current_stock: StockLot[]
  movements: StockMovement[]
  consumed_components: {
    item_code: string
    item_name: string
    lot_no: string | null
    qty: number
    occurred_at: string
  }[]
}

export interface DefectCode {
  id: number
  code: string
  name: string
  category: string
  is_active: boolean
}

export interface InspectionCharacteristic {
  id: number
  plan_id: number
  seq: number
  name: string
  char_type: 'NUMERIC' | 'ATTRIBUTE'
  uom: string | null
  target: number | null
  lower_limit: number | null
  upper_limit: number | null
  method: string | null
}

export interface InspectionPlan {
  id: number
  code: string
  name: string
  item_id: number | null
  inspection_type: InspectionType
  operation_seq: number | null
  sample_size: number
  is_active: boolean
  characteristics: InspectionCharacteristic[]
}

export interface InspectionResult {
  id: number
  characteristic_id: number | null
  characteristic_name: string
  sample_no: number
  value_numeric: number | null
  value_text: string | null
  judgment: Judgment
}

export interface Inspection {
  id: number
  inspection_no: string
  plan_id: number | null
  inspection_type: InspectionType
  item_id: number
  lot_no: string | null
  order_id: number | null
  qty_inspected: number
  qty_accepted: number
  qty_rejected: number
  result: Judgment
  inspected_at: string
  note: string | null
  item: Item
  results: InspectionResult[]
}

export interface Ncr {
  id: number
  ncr_no: string
  item_id: number
  lot_no: string | null
  order_id: number | null
  inspection_id: number | null
  defect_code_id: number | null
  qty: number
  description: string | null
  disposition: Disposition
  status: NcrStatus
  root_cause: string | null
  corrective_action: string | null
  closed_at: string | null
  created_at: string
  item: Item
  defect_code: DefectCode | null
}

export interface Machine {
  id: number
  code: string
  name: string
  work_center_id: number
  ideal_cycle_seconds: number
  is_active: boolean
  status: MachineStatus
  status_since: string | null
  work_center: WorkCenter
}

export interface DowntimeReason {
  id: number
  code: string
  name: string
  category: 'PLANNED' | 'UNPLANNED'
  affects_availability: boolean
}

export interface DowntimeEvent {
  id: number
  machine_id: number
  reason_id: number
  started_at: string
  ended_at: string | null
  duration_minutes: number
  note: string | null
  machine: Machine
  reason: DowntimeReason
}

export interface MaintenanceRequest {
  id: number
  request_no: string
  machine_id: number
  title: string
  description: string | null
  priority: string
  status: string
  closed_at: string | null
  created_at: string
  machine: Machine
}

export interface Oee {
  machine_id: number
  machine_code: string
  machine_name: string
  window_start: string
  window_end: string
  scheduled_minutes: number
  planned_downtime_minutes: number
  unplanned_downtime_minutes: number
  loading_minutes: number
  run_minutes: number
  good_count: number
  scrap_count: number
  total_count: number
  availability: number
  performance: number
  quality: number
  oee: number
}

export interface Dashboard {
  generated_at: string
  window_start: string
  window_end: string
  kpis: { key: string; label: string; value: number; unit: string; hint: string | null }[]
  production_trend: { label: string; good: number; scrap: number; target: number }[]
  order_status: { label: string; value: number }[]
  machine_status: { label: string; value: number }[]
  downtime_pareto: { code: string; name: string; category: string; events: number; minutes: number }[]
  top_defects: { code: string; name: string; count: number; qty: number }[]
  low_stock: {
    item_id: number
    code: string
    name: string
    uom: string
    on_hand: number
    safety_stock: number
    shortfall: number
  }[]
  plant_oee: {
    availability: number
    performance: number
    quality: number
    oee: number
    machines: Oee[]
  }
}

export interface ScanResult {
  kind: 'ORDER' | 'ITEM' | 'LOT' | 'BADGE' | 'UNKNOWN'
  label: string
  id: number | null
  payload: Record<string, unknown>
}

export interface StatusNode {
  key: string
  label: string
  count: number
  terminal: boolean
}

export interface WorkflowEntity {
  key: string
  label: string
  hint: string | null
  statuses: StatusNode[]
  main_path: string[]
  branches: { from: string; to: string; label?: string }[]
}

export interface FlowStage {
  key: string
  label: string
  detail: string | null
  count: number
  unit: string
  secondary: number | null
  kind: 'store' | 'gate' | 'process' | 'reject'
}

export interface WorkflowMap {
  generated_at: string
  flow: FlowStage[]
  reject_branch: FlowStage[]
  entities: WorkflowEntity[]
}

// --- optimization -----------------------------------------------------------
export interface ScheduledOperation {
  order_id: number
  order_no: string
  item_code: string
  operation_id: number
  seq: number
  name: string
  work_center_id: number
  work_center_code: string
  machine_id: number
  machine_code: string
  qty: number
  setup_minutes: number
  run_minutes: number
  start: string
  end: string
  offset_minutes: number
  work_minutes: number
}

export interface ScheduledOrder {
  order_id: number
  order_no: string
  item_code: string
  item_name: string
  qty: number
  priority: number
  due: string | null
  start: string
  end: string
  lateness_hours: number
  operations: ScheduledOperation[]
}

export interface UtilisationRow {
  work_center_id: number
  work_center_code: string
  work_center_name: string
  machines: number
  loaded_hours: number
  capacity_hours: number
  setup_hours: number
  utilisation: number
}

export interface Schedule {
  rule: string
  horizon_start: string
  horizon_end: string
  orders: ScheduledOrder[]
  operations: ScheduledOperation[]
  unscheduled: { order_id: number; order_no: string; item_code: string; reason: string }[]
  day_marks: { label: string; offset_minutes: number }[]
  makespan_hours: number
  total_lateness_hours: number
  max_lateness_hours: number
  late_orders: number
  utilisation: UtilisationRow[]
}

export interface RuleResult {
  rule: string
  description: string
  makespan_hours: number
  total_lateness_hours: number
  max_lateness_hours: number
  late_orders: number
  scheduled_orders: number
  unscheduled_orders: number
}

export interface Comparison {
  objective: string
  objective_label: string
  results: RuleResult[]
  best_rule: string
  baseline_rule: string
  improvement: number
  improvement_pct: number
}

export interface Bottleneck extends UtilisationRow {
  is_constraint: boolean
  idle_capacity_elsewhere_hours: number
  setup_share: number
}

export interface FlowEfficiency {
  orders: number
  work_hours: number
  flow_hours: number
  queue_hours: number
  efficiency: number
}

export interface Recommendation {
  area: 'process' | 'time' | 'cost'
  severity: 'high' | 'medium' | 'low'
  title: string
  detail: string
  action: string
  value: string
}

export interface OrderCost {
  order_id: number
  order_no: string
  item_code: string
  item_name: string
  status: string
  qty_ordered: number
  qty_produced: number
  qty_scrapped: number
  standard_material: number
  standard_labour: number
  standard_total: number
  actual_material: number
  actual_labour: number
  actual_total: number
  material_variance: number
  labour_variance: number
  total_variance: number
  scrap_cost: number
  unit_cost_standard: number
  unit_cost_actual: number
}

export interface CostSummary {
  orders: number
  standard_total: number
  actual_total: number
  total_variance: number
  material_variance: number
  labour_variance: number
  scrap_cost: number
  variance_pct: number
  worst_orders: OrderCost[]
}

export interface SetupSaving {
  item_code: string
  work_center_code: string
  orders: number
  setup_minutes_each: number
  saveable_minutes: number
  saveable_hours: number
  saveable_cost: number
  order_nos: string[]
}

export interface ScrapCost {
  code: string
  name: string
  category: string
  events: number
  qty: number
  cost: number
}

export interface OptimizationReport {
  generated_at: string
  schedule: Schedule
  comparison: Comparison
  bottleneck: Bottleneck | null
  flow: FlowEfficiency
  setups: SetupSaving[]
  cost: CostSummary
  scrap_cost: ScrapCost[]
  recommendations: Recommendation[]
}

// --- calendar ---------------------------------------------------------------
export type CalendarKind = 'ACTUAL' | 'PLANNED' | 'DUE'

export interface CalendarEvent {
  id: string
  kind: CalendarKind
  date: string
  end_date: string | null
  order_id: number
  order_no: string
  item_code: string
  item_name: string
  title: string
  detail: string | null
  status: string
  qty: number
  editable: boolean
}

export interface CalendarFeed {
  start: string
  end: string
  events: CalendarEvent[]
}
