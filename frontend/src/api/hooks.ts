import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'

import { api } from './client'
import type {
  Bom,
  Confirmation,
  Dashboard,
  DefectCode,
  DowntimeEvent,
  DowntimeReason,
  Inspection,
  InspectionPlan,
  Item,
  Location,
  LotTrace,
  Machine,
  MaintenanceRequest,
  Ncr,
  Oee,
  OrderOperation,
  ProductionOrder,
  Routing,
  ScanResult,
  StockLot,
  StockMovement,
  StockOnHand,
  User,
  WorkCenter,
  WorkflowMap,
  OptimizationReport,
  Schedule,
  CalendarFeed,
} from './types'

const get = async <T,>(url: string, params?: Record<string, unknown>): Promise<T> =>
  (await api.get<T>(url, { params })).data

/** Live shop-floor views poll; master data does not. */
const LIVE = { refetchInterval: 30_000 }

// --- dashboard --------------------------------------------------------------
export const useDashboard = (days = 7) =>
  useQuery({
    queryKey: ['dashboard', days],
    queryFn: () => get<Dashboard>('/dashboard', { days }),
    ...LIVE,
  })

export const useWorkflow = () =>
  useQuery({ queryKey: ['workflow'], queryFn: () => get<WorkflowMap>('/workflow'), ...LIVE })

// --- calendar ---------------------------------------------------------------
export const useCalendar = (start: string, end: string) =>
  useQuery({
    queryKey: ['calendar', start, end],
    queryFn: () => get<CalendarFeed>('/calendar', { start, end }),
  })

export const useReschedule = () =>
  useApiMutation<
    {
      orderId: number
      planned_start?: string | null
      planned_end?: string | null
      due_date?: string | null
      move_due_date?: boolean
      reason?: string | null
    },
    unknown
  >(
    ({ orderId, ...body }) =>
      api.patch(`/calendar/orders/${orderId}`, body).then((r) => r.data),
    [['calendar'], ['orders'], ['order'], ['optimization'], ['dashboard'], ['workflow']],
  )

// --- accounts ---------------------------------------------------------------
export const useCreateUser = () =>
  useApiMutation<Record<string, unknown>, User>((body) => post('/auth/users', body), [['users']])

export const useUpdateUser = () =>
  useApiMutation<{ id: number; body: Record<string, unknown> }, User>(
    ({ id, body }) => api.patch(`/auth/users/${id}`, body).then((r) => r.data),
    [['users']],
  )

export const useChangeOwnPassword = () =>
  useApiMutation<{ current_password: string; new_password: string }, User>(
    (body) => post('/auth/me/password', body),
    [],
  )

// --- optimization -----------------------------------------------------------
export const useOptimization = (params: { rule: string; horizon_days: number; objective: string }) =>
  useQuery({
    queryKey: ['optimization', params],
    queryFn: () => get<OptimizationReport>('/optimization', params),
  })

export const useApplySchedule = () =>
  useApiMutation<{ rule: string; horizon_days: number }, Schedule>(
    (body) => post('/optimization/apply', body),
    [['optimization'], ['orders'], ['order'], ['queue'], ['dashboard'], ['workflow']],
  )

// --- master data ------------------------------------------------------------
export const useItems = (params?: { q?: string; item_type?: string }) =>
  useQuery({ queryKey: ['items', params], queryFn: () => get<Item[]>('/master/items', params) })

export const useWorkCenters = () =>
  useQuery({ queryKey: ['work-centers'], queryFn: () => get<WorkCenter[]>('/master/work-centers') })

export const useLocations = () =>
  useQuery({ queryKey: ['locations'], queryFn: () => get<Location[]>('/master/locations') })

export const useBoms = (itemId?: number) =>
  useQuery({
    queryKey: ['boms', itemId ?? null],
    queryFn: () => get<Bom[]>('/master/boms', itemId ? { item_id: itemId } : undefined),
  })

export const useRoutings = (itemId?: number) =>
  useQuery({
    queryKey: ['routings', itemId ?? null],
    queryFn: () => get<Routing[]>('/master/routings', itemId ? { item_id: itemId } : undefined),
  })

// --- production -------------------------------------------------------------
export const useOrders = (params?: { status_filter?: string; open_only?: boolean }) =>
  useQuery({
    queryKey: ['orders', params],
    queryFn: () => get<ProductionOrder[]>('/production/orders', params),
    ...LIVE,
  })

export const useOrder = (orderId: number | null) =>
  useQuery({
    queryKey: ['order', orderId],
    queryFn: () => get<ProductionOrder>(`/production/orders/${orderId}`),
    enabled: orderId != null,
  })

export const useWorkQueue = (workCenterId?: number | null) =>
  useQuery({
    queryKey: ['queue', workCenterId ?? null],
    queryFn: () =>
      get<OrderOperation[]>('/production/queue', workCenterId ? { work_center_id: workCenterId } : undefined),
    ...LIVE,
  })

export const useConfirmations = (orderId?: number) =>
  useQuery({
    queryKey: ['confirmations', orderId ?? null],
    queryFn: () => get<Confirmation[]>('/production/confirmations', orderId ? { order_id: orderId } : undefined),
  })

// --- inventory --------------------------------------------------------------
export const useOnHand = (lowStockOnly = false) =>
  useQuery({
    queryKey: ['on-hand', lowStockOnly],
    queryFn: () => get<StockOnHand[]>('/inventory/on-hand', { low_stock_only: lowStockOnly }),
  })

export const useLots = (params?: { item_id?: number; location_id?: number; lot_no?: string }) =>
  useQuery({ queryKey: ['lots', params], queryFn: () => get<StockLot[]>('/inventory/lots', params) })

export const useMovements = (params?: { item_id?: number; ref_no?: string; lot_no?: string }) =>
  useQuery({
    queryKey: ['movements', params],
    queryFn: () => get<StockMovement[]>('/inventory/movements', params),
  })

export const useTrace = (lotNo: string | null) =>
  useQuery({
    queryKey: ['trace', lotNo],
    queryFn: () => get<LotTrace>(`/inventory/trace/${encodeURIComponent(lotNo!)}`),
    enabled: !!lotNo,
    retry: false,
  })

// --- quality ----------------------------------------------------------------
export const useDefectCodes = () =>
  useQuery({ queryKey: ['defect-codes'], queryFn: () => get<DefectCode[]>('/quality/defect-codes') })

export const useInspectionPlans = (itemId?: number) =>
  useQuery({
    queryKey: ['plans', itemId ?? null],
    queryFn: () => get<InspectionPlan[]>('/quality/plans', itemId ? { item_id: itemId } : undefined),
  })

export const useInspections = (params?: { order_id?: number; result?: string }) =>
  useQuery({ queryKey: ['inspections', params], queryFn: () => get<Inspection[]>('/quality/inspections', params) })

export const useNcrs = (statusFilter?: string) =>
  useQuery({
    queryKey: ['ncrs', statusFilter ?? null],
    queryFn: () => get<Ncr[]>('/quality/ncrs', statusFilter ? { status_filter: statusFilter } : undefined),
  })

// --- equipment --------------------------------------------------------------
export const useMachines = () =>
  useQuery({ queryKey: ['machines'], queryFn: () => get<Machine[]>('/equipment/machines'), ...LIVE })

export const useDowntimeReasons = () =>
  useQuery({ queryKey: ['downtime-reasons'], queryFn: () => get<DowntimeReason[]>('/equipment/downtime-reasons') })

export const useDowntime = (params?: { machine_id?: number; open_only?: boolean; days?: number }) =>
  useQuery({
    queryKey: ['downtime', params],
    queryFn: () => get<DowntimeEvent[]>('/equipment/downtime', params),
    ...LIVE,
  })

export const useMaintenance = (openOnly = true) =>
  useQuery({
    queryKey: ['maintenance', openOnly],
    queryFn: () => get<MaintenanceRequest[]>('/equipment/maintenance', { open_only: openOnly }),
  })

export const useOee = (days = 1) =>
  useQuery({ queryKey: ['oee', days], queryFn: () => get<Oee[]>('/equipment/oee', { days }), ...LIVE })

// --- users ------------------------------------------------------------------
export const useUsers = (enabled = true) =>
  useQuery({ queryKey: ['users'], queryFn: () => get<User[]>('/auth/users'), enabled })

// --- mutations --------------------------------------------------------------
/**
 * Every write invalidates the query keys it can affect. Listing them explicitly
 * beats a blanket invalidateQueries() - the live shop-floor views would
 * otherwise refetch on every keystroke-driven mutation.
 */
function useApiMutation<TBody, TResult>(
  request: (body: TBody) => Promise<TResult>,
  invalidate: QueryKey[],
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      invalidate.forEach((key) => queryClient.invalidateQueries({ queryKey: key }))
    },
  })
}

const post = async <T,>(url: string, body?: unknown): Promise<T> => (await api.post<T>(url, body)).data

export const useCreateOrder = () =>
  useApiMutation<Record<string, unknown>, ProductionOrder>(
    (body) => post('/production/orders', body),
    [['orders'], ['dashboard'], ['queue']],
  )

export const useReleaseOrder = () =>
  useApiMutation<number, ProductionOrder>(
    (id) => post(`/production/orders/${id}/release`),
    [['orders'], ['order'], ['queue'], ['dashboard']],
  )

export const useCloseOrder = () =>
  useApiMutation<number, ProductionOrder>(
    (id) => post(`/production/orders/${id}/close`),
    [['orders'], ['order'], ['queue'], ['dashboard']],
  )

export const useCancelOrder = () =>
  useApiMutation<number, ProductionOrder>(
    (id) => post(`/production/orders/${id}/cancel`),
    [['orders'], ['order'], ['queue'], ['dashboard']],
  )

export const useIssueMaterial = () =>
  useApiMutation<{ orderId: number; material_id: number; qty: number; from_location_id?: number }, ProductionOrder>(
    ({ orderId, ...body }) => post(`/production/orders/${orderId}/issue`, body),
    [['order'], ['orders'], ['on-hand'], ['lots'], ['movements'], ['items']],
  )

export const useConfirm = () =>
  useApiMutation<Record<string, unknown>, Confirmation>(
    (body) => post('/production/confirmations', body),
    [
      ['order'], ['orders'], ['queue'], ['dashboard'], ['oee'],
      ['confirmations'], ['lots'], ['on-hand'], ['items'],
    ],
  )

export const useScan = () =>
  useMutation({ mutationFn: (code: string) => post<ScanResult>('/production/scan', { code }) })

export const useGoodsReceipt = () =>
  useApiMutation<Record<string, unknown>, StockLot>(
    (body) => post('/inventory/receipts', body),
    [['on-hand'], ['lots'], ['movements'], ['items'], ['dashboard']],
  )

export const useTransfer = () =>
  useApiMutation<Record<string, unknown>, StockMovement>(
    (body) => post('/inventory/transfers', body),
    [['on-hand'], ['lots'], ['movements']],
  )

export const useAdjust = () =>
  useApiMutation<Record<string, unknown>, StockMovement>(
    (body) => post('/inventory/adjustments', body),
    [['on-hand'], ['lots'], ['movements'], ['items'], ['dashboard']],
  )

export const useRecordInspection = () =>
  useApiMutation<Record<string, unknown>, Inspection>(
    (body) => post('/quality/inspections', body),
    [['inspections'], ['ncrs'], ['lots'], ['on-hand'], ['dashboard'], ['order']],
  )

export const useUpdateNcr = () =>
  useApiMutation<{ id: number; body: Record<string, unknown> }, Ncr>(
    async ({ id, body }) => (await api.patch<Ncr>(`/quality/ncrs/${id}`, body)).data,
    [['ncrs'], ['lots'], ['on-hand'], ['dashboard']],
  )

export const useSetMachineStatus = () =>
  useApiMutation<{ id: number; status: string; reason_id?: number; note?: string }, Machine>(
    ({ id, ...body }) => post(`/equipment/machines/${id}/status`, body),
    [['machines'], ['downtime'], ['oee'], ['dashboard']],
  )

export const useEndDowntime = () =>
  useApiMutation<number, DowntimeEvent>(
    (id) => post(`/equipment/downtime/${id}/end`, {}),
    [['machines'], ['downtime'], ['oee'], ['dashboard']],
  )

export const useCreateMaintenance = () =>
  useApiMutation<Record<string, unknown>, MaintenanceRequest>(
    (body) => post('/equipment/maintenance', body),
    [['maintenance']],
  )

export const useCloseMaintenance = () =>
  useApiMutation<number, MaintenanceRequest>(
    (id) => post(`/equipment/maintenance/${id}/close`, {}),
    [['maintenance']],
  )

export const useCreateItem = () =>
  useApiMutation<Record<string, unknown>, Item>((body) => post('/master/items', body), [['items'], ['on-hand']])
