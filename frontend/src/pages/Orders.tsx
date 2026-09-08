import { useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { errorMessage } from '../api/client'
import { useCreateOrder, useItems, useOrders } from '../api/hooks'
import type { OrderStatus } from '../api/types'
import { Layout } from '../components/Layout'
import { Alert, Card, Empty, Field, Loading, Meter, Modal, OrderBadge } from '../components/ui'
import { dateTime, qty, toLocalInput } from '../lib/format'
import { useAuth } from '../lib/auth'

const STATUSES: (OrderStatus | 'ALL' | 'OPEN')[] = [
  'OPEN',
  'DRAFT',
  'RELEASED',
  'IN_PROGRESS',
  'COMPLETED',
  'CLOSED',
  'CANCELLED',
  'ALL',
]

export function Orders() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const [filter, setFilter] = useState<OrderStatus | 'ALL' | 'OPEN'>('OPEN')
  const [creating, setCreating] = useState(false)

  const params = useMemo(() => {
    if (filter === 'ALL') return undefined
    if (filter === 'OPEN') return { open_only: true }
    return { status_filter: filter }
  }, [filter])

  const { data: orders, isLoading, error } = useOrders(params)

  return (
    <Layout
      title="Work orders"
      subtitle="Everything the plant is building, has built, or is queued to build"
      actions={
        can('PLANNER') ? (
          <button className="primary" onClick={() => setCreating(true)}>
            + New order
          </button>
        ) : undefined
      }
    >
      <div className="stack">
        <div className="tabs">
          {STATUSES.map((status) => (
            <button
              key={status}
              className={filter === status ? 'active' : ''}
              onClick={() => setFilter(status)}
            >
              {status === 'OPEN' ? 'Open' : status === 'ALL' ? 'All' : status.replace('_', ' ').toLowerCase()}
            </button>
          ))}
        </div>

        {error && <Alert tone="error">{errorMessage(error)}</Alert>}
        {isLoading && <Loading />}

        {orders && (
          <Card flush>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Product</th>
                    <th className="num">Ordered</th>
                    <th className="num">Produced</th>
                    <th style={{ width: 140 }}>Progress</th>
                    <th className="num">Scrap</th>
                    <th>Status</th>
                    <th>Planned end</th>
                    <th className="num">Pri</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.length === 0 && (
                    <tr>
                      <td colSpan={9}>
                        <Empty>No orders match this filter</Empty>
                      </td>
                    </tr>
                  )}
                  {orders.map((order) => {
                    const progress = order.qty_ordered ? order.qty_produced / order.qty_ordered : 0
                    const late =
                      order.planned_end != null &&
                      new Date(order.planned_end) < new Date() &&
                      ['RELEASED', 'IN_PROGRESS'].includes(order.status)
                    return (
                      <tr
                        key={order.id}
                        className="clickable"
                        onClick={() => navigate(`/orders/${order.id}`)}
                      >
                        <td className="code strong">{order.order_no}</td>
                        <td>
                          <div className="strong">{order.item.name}</div>
                          <div className="muted small code">{order.item.code}</div>
                        </td>
                        <td className="num">{qty(order.qty_ordered)}</td>
                        <td className="num">{qty(order.qty_produced)}</td>
                        <td>
                          <Meter value={progress} tone={progress >= 1 ? 'good' : undefined} />
                        </td>
                        <td className="num">{order.qty_scrapped ? qty(order.qty_scrapped) : '-'}</td>
                        <td>
                          <OrderBadge status={order.status} />
                        </td>
                        <td className={late ? 'strong' : 'secondary'} style={late ? { color: 'var(--critical)' } : undefined}>
                          {dateTime(order.planned_end)}
                          {late && ' · late'}
                        </td>
                        <td className="num">{order.priority}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>

      {creating && <NewOrderModal onClose={() => setCreating(false)} />}
    </Layout>
  )
}

function NewOrderModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { data: items } = useItems()
  const createOrder = useCreateOrder()

  const producible = (items ?? []).filter(
    (item) => item.item_type === 'FINISHED_GOOD' || item.item_type === 'SUB_ASSEMBLY',
  )

  const [itemId, setItemId] = useState<number | ''>('')
  const [quantity, setQuantity] = useState('50')
  const [priority, setPriority] = useState('5')
  const [salesRef, setSalesRef] = useState('')
  const tomorrow = new Date(Date.now() + 86_400_000)
  const [start, setStart] = useState(toLocalInput(new Date(tomorrow.setHours(8, 0, 0, 0))))
  const [end, setEnd] = useState(toLocalInput(new Date(new Date(tomorrow).setHours(17, 0, 0, 0))))
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      const order = await createOrder.mutateAsync({
        item_id: Number(itemId),
        qty_ordered: Number(quantity),
        priority: Number(priority),
        planned_start: start ? new Date(start).toISOString() : null,
        planned_end: end ? new Date(end).toISOString() : null,
        sales_ref: salesRef || null,
      })
      onClose()
      navigate(`/orders/${order.id}`)
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title="New work order"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary"
            form="new-order"
            type="submit"
            disabled={!itemId || createOrder.isPending}
          >
            {createOrder.isPending ? 'Creating...' : 'Create order'}
          </button>
        </>
      }
    >
      <form id="new-order" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Product" note="only items with an active routing can be built">
          <select value={itemId} onChange={(event) => setItemId(Number(event.target.value))} required>
            <option value="">Select a product...</option>
            {producible.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} - {item.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Quantity">
              <input type="number" min="1" step="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} required />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Priority" note="1 = highest">
              <input type="number" min="1" max="9" value={priority} onChange={(e) => setPriority(e.target.value)} />
            </Field>
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Planned start">
              <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Planned end">
              <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
        </div>
        <Field label="Sales reference" note="optional">
          <input value={salesRef} onChange={(e) => setSalesRef(e.target.value)} placeholder="SO-41234" />
        </Field>
      </form>
    </Modal>
  )
}
