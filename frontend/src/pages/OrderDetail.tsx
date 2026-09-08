import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { errorMessage } from '../api/client'
import {
  useCancelOrder,
  useCloseOrder,
  useConfirmations,
  useIssueMaterial,
  useLocations,
  useOrder,
  useReleaseOrder,
} from '../api/hooks'
import type { OrderMaterial } from '../api/types'
import { Layout } from '../components/Layout'
import {
  Alert,
  Card,
  Empty,
  Field,
  Loading,
  Meter,
  Modal,
  OperationBadge,
  OrderBadge,
} from '../components/ui'
import { useAuth } from '../lib/auth'
import { dateTime, duration, qty } from '../lib/format'

export function OrderDetail() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const { can } = useAuth()
  const id = Number(orderId)

  const { data: order, isLoading, error } = useOrder(Number.isFinite(id) ? id : null)
  const { data: confirmations } = useConfirmations(Number.isFinite(id) ? id : undefined)
  const release = useReleaseOrder()
  const close = useCloseOrder()
  const cancel = useCancelOrder()

  const [issuing, setIssuing] = useState<OrderMaterial | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setActionError(null)
    try {
      await action()
    } catch (exception) {
      setActionError(errorMessage(exception))
    }
  }

  if (isLoading) {
    return (
      <Layout title="Work order">
        <Loading />
      </Layout>
    )
  }
  if (error || !order) {
    return (
      <Layout title="Work order">
        <Alert tone="error">{error ? errorMessage(error) : 'Order not found'}</Alert>
      </Layout>
    )
  }

  const progress = order.qty_ordered ? order.qty_produced / order.qty_ordered : 0
  const materialsShort = (order.materials ?? []).filter((line) => line.qty_open > 0.0001)

  return (
    <Layout
      title={order.order_no}
      subtitle={
        <>
          {order.item.code} · {order.item.name}
          {order.sales_ref && ` · ${order.sales_ref}`}
        </>
      }
      actions={
        <>
          <button onClick={() => navigate('/orders')}>← All orders</button>
          {can('PLANNER') && order.status === 'DRAFT' && (
            <>
              <button className="primary" onClick={() => run(() => release.mutateAsync(order.id))}>
                Release
              </button>
              <button className="danger" onClick={() => run(() => cancel.mutateAsync(order.id))}>
                Cancel
              </button>
            </>
          )}
          {can('PLANNER') && (order.status === 'COMPLETED' || order.status === 'IN_PROGRESS') && (
            <button onClick={() => run(() => close.mutateAsync(order.id))}>Close order</button>
          )}
          {['RELEASED', 'IN_PROGRESS'].includes(order.status) && (
            <Link className="btn primary" to={`/terminal?order=${order.order_no}`}>
              Open on shop floor
            </Link>
          )}
        </>
      }
    >
      <div className="stack">
        {actionError && <Alert tone="error">{actionError}</Alert>}

        <div className="kpis">
          <div className="kpi">
            <div className="label">Status</div>
            <div style={{ marginTop: 8 }}>
              <OrderBadge status={order.status} />
            </div>
            <div className="hint">Priority {order.priority}</div>
          </div>
          <div className="kpi">
            <div className="label">Ordered</div>
            <div className="value">
              {qty(order.qty_ordered)}
              <span className="unit">{order.item.uom}</span>
            </div>
          </div>
          <div className="kpi">
            <div className="label">Produced</div>
            <div className="value">{qty(order.qty_produced)}</div>
            <div style={{ marginTop: 8 }}>
              <Meter value={progress} tone={progress >= 1 ? 'good' : undefined} />
            </div>
          </div>
          <div className="kpi">
            <div className="label">Scrapped</div>
            <div className="value">{qty(order.qty_scrapped)}</div>
            <div className="hint">
              {order.qty_produced + order.qty_scrapped > 0
                ? `${((order.qty_produced / (order.qty_produced + order.qty_scrapped)) * 100).toFixed(1)}% yield`
                : 'No output yet'}
            </div>
          </div>
          <div className="kpi">
            <div className="label">Output lot</div>
            <div className="value" style={{ fontSize: 17 }}>
              {order.output_lot_no ? (
                <Link className="code" to={`/inventory?trace=${order.output_lot_no}`}>
                  {order.output_lot_no}
                </Link>
              ) : (
                <span className="muted">Not assigned</span>
              )}
            </div>
            <div className="hint">Assigned at release</div>
          </div>
          <div className="kpi">
            <div className="label">Schedule</div>
            <div className="hint" style={{ marginTop: 6 }}>
              Planned {dateTime(order.planned_start)}
              <br />
              to {dateTime(order.planned_end)}
            </div>
          </div>
        </div>

        {materialsShort.length > 0 && ['RELEASED', 'IN_PROGRESS'].includes(order.status) && (
          <Alert tone="info">
            {materialsShort.length} material line{materialsShort.length > 1 ? 's have' : ' has'} not been fully
            issued. The floor can still report, but stock will not reconcile until the kit is complete.
          </Alert>
        )}

        <Card title="Routing" hint="Steps are frozen from the routing at order creation" flush>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Seq</th>
                  <th>Operation</th>
                  <th>Work centre</th>
                  <th className="num">Completed</th>
                  <th className="num">Scrap</th>
                  <th>Status</th>
                  <th>QC</th>
                  <th>Started</th>
                  <th>Finished</th>
                </tr>
              </thead>
              <tbody>
                {(order.operations ?? []).map((operation) => (
                  <tr key={operation.id}>
                    <td className="num code">{operation.seq}</td>
                    <td>
                      <div className="strong">{operation.name}</div>
                      {operation.instructions && (
                        <div className="muted small">{operation.instructions}</div>
                      )}
                    </td>
                    <td>
                      <span className="code">{operation.work_center.code}</span>
                      <div className="muted small">{operation.work_center.name}</div>
                    </td>
                    <td className="num">{qty(operation.qty_completed)}</td>
                    <td className="num">{operation.qty_scrapped ? qty(operation.qty_scrapped) : '-'}</td>
                    <td>
                      <OperationBadge status={operation.status} />
                    </td>
                    <td>{operation.requires_inspection ? 'Required' : <span className="muted">-</span>}</td>
                    <td className="secondary small">{dateTime(operation.actual_start)}</td>
                    <td className="secondary small">{dateTime(operation.actual_end)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          title="Material requirement"
          hint="Quantities include the scrap allowance from the BOM"
          flush
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Line</th>
                  <th>Component</th>
                  <th className="num">Required</th>
                  <th className="num">Issued</th>
                  <th className="num">Open</th>
                  <th className="num">At op</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(order.materials ?? []).length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <Empty>This order has no BOM attached</Empty>
                    </td>
                  </tr>
                )}
                {(order.materials ?? []).map((material) => (
                  <tr key={material.id}>
                    <td className="num code">{material.line_no}</td>
                    <td>
                      <span className="code strong">{material.component.code}</span>
                      <div className="muted small">{material.component.name}</div>
                    </td>
                    <td className="num">
                      {qty(material.qty_required)} <span className="muted">{material.component.uom}</span>
                    </td>
                    <td className="num">{qty(material.qty_issued)}</td>
                    <td className="num" style={material.qty_open > 0.0001 ? { color: 'var(--critical)' } : undefined}>
                      {material.qty_open > 0.0001 ? qty(material.qty_open) : '-'}
                    </td>
                    <td className="num muted">{material.operation_seq ?? '-'}</td>
                    <td className="num">
                      {can('WAREHOUSE', 'OPERATOR', 'PLANNER') &&
                        material.qty_open > 0.0001 &&
                        ['RELEASED', 'IN_PROGRESS'].includes(order.status) && (
                          <button className="sm" onClick={() => setIssuing(material)}>
                            Issue
                          </button>
                        )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Production reports" hint="Every confirmation booked against this order" flush>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Finished</th>
                  <th className="num">Good</th>
                  <th className="num">Scrap</th>
                  <th className="num">Duration</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {(confirmations ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <Empty>Nothing reported yet</Empty>
                    </td>
                  </tr>
                )}
                {(confirmations ?? []).map((confirmation) => (
                  <tr key={confirmation.id}>
                    <td className="secondary">{dateTime(confirmation.ended_at)}</td>
                    <td className="num strong">{qty(confirmation.qty_good)}</td>
                    <td className="num">{confirmation.qty_scrap ? qty(confirmation.qty_scrap) : '-'}</td>
                    <td className="num secondary">{duration(confirmation.duration_minutes)}</td>
                    <td className="muted small">{confirmation.note ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {issuing && <IssueModal orderId={order.id} material={issuing} onClose={() => setIssuing(null)} />}
    </Layout>
  )
}

function IssueModal({
  orderId,
  material,
  onClose,
}: {
  orderId: number
  material: OrderMaterial
  onClose: () => void
}) {
  const { data: locations } = useLocations()
  const issue = useIssueMaterial()
  const [amount, setAmount] = useState(String(material.qty_open))
  const [locationId, setLocationId] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)

  const rawLocations = (locations ?? []).filter((location) => location.location_type === 'RAW')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await issue.mutateAsync({
        orderId,
        material_id: material.id,
        qty: Number(amount),
        from_location_id: locationId === '' ? undefined : Number(locationId),
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title={`Issue ${material.component.code}`}
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="issue-form" type="submit" disabled={issue.isPending}>
            {issue.isPending ? 'Issuing...' : 'Issue material'}
          </button>
        </>
      }
    >
      <form id="issue-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <div className="secondary small">
          {material.component.name} · required {qty(material.qty_required)} {material.component.uom} · already
          issued {qty(material.qty_issued)}
        </div>
        <Field label="Quantity to issue">
          <input
            type="number"
            step="0.001"
            min="0.001"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            required
            autoFocus
          />
        </Field>
        <Field label="Pick from" note="lots are consumed oldest first">
          <select value={locationId} onChange={(event) => setLocationId(Number(event.target.value))}>
            <option value="">Any raw store</option>
            {rawLocations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.code} - {location.name}
              </option>
            ))}
          </select>
        </Field>
      </form>
    </Modal>
  )
}
