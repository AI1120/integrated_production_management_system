/**
 * One source of truth for what every status *means* visually.
 *
 * Badges and the workflow diagram both read these maps, so a status can never
 * be green in one place and red in another.
 */
import type {
  Disposition,
  Judgment,
  LotStatus,
  MachineStatus,
  NcrStatus,
  OperationStatus,
  OrderStatus,
} from '../api/types'

export type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'info'

export const ORDER_TONE: Record<OrderStatus, Tone> = {
  DRAFT: 'neutral',
  RELEASED: 'info',
  IN_PROGRESS: 'warn',
  COMPLETED: 'good',
  CLOSED: 'neutral',
  CANCELLED: 'bad',
}

export const OPERATION_TONE: Record<OperationStatus, Tone> = {
  PENDING: 'neutral',
  SETUP: 'info',
  RUNNING: 'warn',
  PAUSED: 'neutral',
  COMPLETED: 'good',
  SKIPPED: 'neutral',
}

export const MACHINE_TONE: Record<MachineStatus, Tone> = {
  IDLE: 'neutral',
  SETUP: 'info',
  RUNNING: 'good',
  DOWN: 'bad',
  MAINTENANCE: 'warn',
}

export const LOT_TONE: Record<LotStatus, Tone> = {
  AVAILABLE: 'good',
  QUARANTINE: 'warn',
  REJECTED: 'bad',
  CONSUMED: 'neutral',
}

export const JUDGMENT_TONE: Record<Judgment, Tone> = {
  PASS: 'good',
  FAIL: 'bad',
  PENDING: 'neutral',
}

export const NCR_TONE: Record<NcrStatus, Tone> = {
  OPEN: 'bad',
  IN_REVIEW: 'warn',
  CLOSED: 'good',
}

export const DISPOSITION_TONE: Record<Disposition, Tone> = {
  PENDING: 'neutral',
  REWORK: 'warn',
  SCRAP: 'bad',
  USE_AS_IS: 'good',
  RETURN_TO_SUPPLIER: 'warn',
}

/** Keyed by the `key` the /api/workflow endpoint gives each entity. */
export const TONE_BY_ENTITY: Record<string, Record<string, Tone>> = {
  production_order: ORDER_TONE,
  operation: OPERATION_TONE,
  stock_lot: LOT_TONE,
  inspection: JUDGMENT_TONE,
  ncr: NCR_TONE,
  disposition: DISPOSITION_TONE,
  machine: MACHINE_TONE,
}

export const toneFor = (entityKey: string, statusKey: string): Tone =>
  TONE_BY_ENTITY[entityKey]?.[statusKey] ?? 'neutral'
