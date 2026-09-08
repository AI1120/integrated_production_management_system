import type { ReactNode } from 'react'

import type { Judgment, LotStatus, MachineStatus, NcrStatus, OperationStatus, OrderStatus } from '../api/types'
import { titleCase } from '../lib/format'
import {
  JUDGMENT_TONE,
  LOT_TONE,
  MACHINE_TONE,
  NCR_TONE,
  OPERATION_TONE,
  ORDER_TONE,
  type Tone,
} from '../lib/status'

export function Card({
  title,
  hint,
  actions,
  children,
  flush,
}: {
  title?: ReactNode
  hint?: ReactNode
  actions?: ReactNode
  children: ReactNode
  flush?: boolean
}) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {hint && <div className="hint">{hint}</div>}
          </div>
          {actions && <div className="row tight">{actions}</div>}
        </header>
      )}
      <div className={flush ? 'card-body flush' : 'card-body'}>{children}</div>
    </section>
  )
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`badge ${tone}`}>
      <span className="dot" aria-hidden="true" />
      {children}
    </span>
  )
}

export const OrderBadge = ({ status }: { status: OrderStatus }) => (
  <Badge tone={ORDER_TONE[status]}>{titleCase(status)}</Badge>
)
export const OperationBadge = ({ status }: { status: OperationStatus }) => (
  <Badge tone={OPERATION_TONE[status]}>{titleCase(status)}</Badge>
)
export const MachineBadge = ({ status }: { status: MachineStatus }) => (
  <Badge tone={MACHINE_TONE[status]}>{titleCase(status)}</Badge>
)
export const LotBadge = ({ status }: { status: LotStatus }) => (
  <Badge tone={LOT_TONE[status]}>{titleCase(status)}</Badge>
)
export const JudgmentBadge = ({ result }: { result: Judgment }) => (
  <Badge tone={JUDGMENT_TONE[result]}>{titleCase(result)}</Badge>
)
export const NcrBadge = ({ status }: { status: NcrStatus }) => (
  <Badge tone={NCR_TONE[status]}>{titleCase(status)}</Badge>
)

export function Field({
  label,
  note,
  children,
}: {
  label: string
  note?: string
  children: ReactNode
}) {
  return (
    <label className="field">
      <span>
        {label} {note && <span className="note">{note}</span>}
      </span>
      {children}
    </label>
  )
}

export function Alert({ tone = 'info', children }: { tone?: 'error' | 'ok' | 'info'; children: ReactNode }) {
  const icon = tone === 'error' ? '!' : tone === 'ok' ? '✓' : 'i'
  return (
    <div className={`alert ${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      <span className="icon" aria-hidden="true">
        {icon}
      </span>
      <div>{children}</div>
    </div>
  )
}

export function Modal({
  title,
  onClose,
  children,
  footer,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div
      className="modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="modal">
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="ghost sm" onClick={onClose} aria-label="Close">
            &#x2715;
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  )
}

export function Meter({ value, tone }: { value: number; tone?: 'good' | 'warn' | 'bad' }) {
  const clamped = Math.max(0, Math.min(1, value || 0))
  return (
    <div className={`meter ${tone ?? ''}`} role="img" aria-label={`${Math.round(clamped * 100)} percent`}>
      <span style={{ width: `${clamped * 100}%` }} />
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Loading() {
  return <div className="empty">Loading...</div>
}

/**
 * Ranked rows with an inline magnitude bar. Preferred over a bar chart when the
 * label matters as much as the value - Pareto lists, stock shortfalls, defects.
 */
export function RankList({
  rows,
  emptyText = 'Nothing to show',
}: {
  rows: { key: string; label: ReactNode; sub?: ReactNode; value: number; display: string }[]
  emptyText?: string
}) {
  if (!rows.length) return <Empty>{emptyText}</Empty>
  const max = Math.max(...rows.map((row) => row.value), 1)
  return (
    <div className="rank-list">
      {rows.map((row) => (
        <div className="rank-row" key={row.key}>
          <div className="rank-label">{row.label}</div>
          <div className="rank-value">{row.display}</div>
          {row.sub && <div className="rank-sub">{row.sub}</div>}
          <div className="rank-bar">
            <span style={{ width: `${(row.value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}
