import { useMemo, useState, type DragEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { errorMessage } from '../api/client'
import { useCalendar, useCancelOrder, useReschedule } from '../api/hooks'
import type { CalendarEvent } from '../api/types'
import { Layout } from '../components/Layout'
import { Alert, Card, Field, Loading, Modal, OrderBadge } from '../components/ui'
import { useAuth } from '../lib/auth'
import { toLocalInput } from '../lib/format'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Local YYYY-MM-DD. toISOString() would shift the day for anyone east of UTC. */
const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

const addDays = (d: Date, n: number) => {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + n)
  return copy
}

/** Monday-first grid covering the whole month plus its overflow weeks. */
function monthGrid(anchor: Date): Date[] {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const offset = (first.getDay() + 6) % 7
  const start = addDays(first, -offset)
  return Array.from({ length: 42 }, (_, i) => addDays(start, i))
}

export function CalendarPage() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const [anchor, setAnchor] = useState(() => new Date())
  const [selected, setSelected] = useState<CalendarEvent | null>(null)
  const [dragging, setDragging] = useState<CalendarEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const days = useMemo(() => monthGrid(anchor), [anchor])
  const { data, isLoading } = useCalendar(iso(days[0]), iso(days[days.length - 1]))
  const reschedule = useReschedule()

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const event of data?.events ?? []) {
      // A planned order occupies every day it spans, not just its start.
      const from = new Date(`${event.date}T00:00:00`)
      const to = event.end_date ? new Date(`${event.end_date}T00:00:00`) : from
      for (let d = new Date(from); d <= to; d = addDays(d, 1)) {
        const key = iso(d)
        if (!map.has(key)) map.set(key, [])
        map.get(key)!.push(event)
      }
    }
    return map
  }, [data])

  const today = iso(new Date())
  const monthLabel = anchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

  async function dropOn(day: Date, event: DragEvent) {
    event.preventDefault()
    if (!dragging || !dragging.editable) return
    const moved = dragging
    setDragging(null)
    setError(null)
    try {
      if (moved.kind === 'DUE') {
        setSelected(moved)
        setNotice('Moving a due date is a re-promise — open it and give a reason.')
        return
      }
      // Preserve the order's duration; only shift where it starts.
      const from = new Date(`${moved.date}T00:00:00`)
      const to = new Date(`${(moved.end_date ?? moved.date)}T00:00:00`)
      const span = Math.round((to.getTime() - from.getTime()) / 86_400_000)
      const start = new Date(day)
      start.setHours(8, 0, 0, 0)
      const end = addDays(new Date(start), span)
      end.setHours(17, 0, 0, 0)
      await reschedule.mutateAsync({
        orderId: moved.order_id,
        planned_start: start.toISOString(),
        planned_end: end.toISOString(),
      })
      setNotice(`${moved.order_no} re-planned to start ${start.toLocaleDateString()}.`)
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Layout
      title="Production calendar"
      subtitle="What the floor did, what is planned, and what is promised"
      actions={
        <>
          <button onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1))}>
            ‹
          </button>
          <button onClick={() => setAnchor(new Date())}>Today</button>
          <button onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1))}>
            ›
          </button>
          {can('PLANNER') && (
            <button className="primary" onClick={() => navigate('/orders')}>
              + New order
            </button>
          )}
        </>
      }
    >
      <div className="stack">
        {error && <Alert tone="error">{error}</Alert>}
        {notice && <Alert tone="ok">{notice}</Alert>}

        <Card
          title={monthLabel}
          hint={
            can('PLANNER')
              ? 'Drag a planned order to re-plan it. Click any item to open it.'
              : 'Click any item to open it.'
          }
          actions={
            <div className="cal-legend">
              <span className="key">
                <span className="chip actual" /> Done
              </span>
              <span className="key">
                <span className="chip planned" /> Planned
              </span>
              <span className="key">
                <span className="chip due" /> Due
              </span>
            </div>
          }
          flush
        >
          {isLoading && <Loading />}
          {!isLoading && (
            <div className="cal">
              {WEEKDAYS.map((day) => (
                <div className="cal-head" key={day}>
                  {day}
                </div>
              ))}
              {days.map((day) => {
                const key = iso(day)
                const events = byDay.get(key) ?? []
                const otherMonth = day.getMonth() !== anchor.getMonth()
                const weekend = day.getDay() === 0 || day.getDay() === 6
                return (
                  <div
                    key={key}
                    className={`cal-day${otherMonth ? ' muted-day' : ''}${weekend ? ' weekend' : ''}${
                      key === today ? ' today' : ''
                    }`}
                    onDragOver={(e) => dragging && e.preventDefault()}
                    onDrop={(e) => dropOn(day, e)}
                  >
                    <div className="cal-date">{day.getDate()}</div>
                    <div className="cal-events">
                      {events.slice(0, 4).map((event) => (
                        <button
                          key={`${event.id}-${key}`}
                          className={`cal-chip ${event.kind.toLowerCase()}`}
                          draggable={event.editable && can('PLANNER')}
                          onDragStart={() => setDragging(event)}
                          onDragEnd={() => setDragging(null)}
                          onClick={() => setSelected(event)}
                          title={`${event.title}${event.detail ? ` — ${event.detail}` : ''}`}
                        >
                          {event.kind === 'DUE' ? '◆ ' : ''}
                          {event.kind === 'ACTUAL' ? event.order_no.replace('WO-', '') : event.order_no.replace('WO-', '')}
                          <span className="cal-chip-sub">
                            {event.kind === 'ACTUAL' ? event.title.replace(/^OP /, 'op') : event.item_code}
                          </span>
                        </button>
                      ))}
                      {events.length > 4 && (
                        <div className="cal-more">+{events.length - 4} more</div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div>

      {selected && (
        <EventModal
          event={selected}
          onClose={() => setSelected(null)}
          onDone={(message) => {
            setSelected(null)
            setNotice(message)
          }}
        />
      )}
    </Layout>
  )
}

function EventModal({
  event,
  onClose,
  onDone,
}: {
  event: CalendarEvent
  onClose: () => void
  onDone: (message: string) => void
}) {
  const navigate = useNavigate()
  const { can } = useAuth()
  const reschedule = useReschedule()
  const cancel = useCancelOrder()

  const [start, setStart] = useState(() => {
    const d = new Date(`${event.date}T08:00:00`)
    return toLocalInput(d)
  })
  const [end, setEnd] = useState(() => {
    const d = new Date(`${(event.end_date ?? event.date)}T17:00:00`)
    return toLocalInput(d)
  })
  const [moveDue, setMoveDue] = useState(event.kind === 'DUE')
  const [dueDate, setDueDate] = useState(() => toLocalInput(new Date(`${event.date}T17:00:00`)))
  const [reason, setReason] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  const editable = event.editable && can('PLANNER')

  async function save(submitEvent: FormEvent) {
    submitEvent.preventDefault()
    setLocalError(null)
    try {
      await reschedule.mutateAsync({
        orderId: event.order_id,
        planned_start: moveDue ? undefined : new Date(start).toISOString(),
        planned_end: moveDue ? undefined : new Date(end).toISOString(),
        due_date: moveDue ? new Date(dueDate).toISOString() : undefined,
        move_due_date: moveDue,
        reason: moveDue ? reason : undefined,
      })
      onDone(
        moveDue
          ? `${event.order_no} re-promised for ${new Date(dueDate).toLocaleDateString()}.`
          : `${event.order_no} re-planned.`,
      )
    } catch (exception) {
      setLocalError(errorMessage(exception))
    }
  }

  async function removeWork() {
    setLocalError(null)
    try {
      await cancel.mutateAsync(event.order_id)
      onDone(`${event.order_no} cancelled.`)
    } catch (exception) {
      setLocalError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title={`${event.order_no} · ${event.item_code}`}
      onClose={onClose}
      footer={
        <>
          <button onClick={() => navigate(`/orders/${event.order_id}`)}>Open order</button>
          <div className="spacer" />
          {editable && event.kind !== 'ACTUAL' && (
            <button className="danger" onClick={removeWork} disabled={cancel.isPending}>
              Cancel order
            </button>
          )}
          {editable && (
            <button className="primary" form="cal-form" type="submit" disabled={reschedule.isPending}>
              {reschedule.isPending ? 'Saving...' : 'Save'}
            </button>
          )}
          {!editable && <button onClick={onClose}>Close</button>}
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        {localError && <Alert tone="error">{localError}</Alert>}

        <div className="row" style={{ gap: 20 }}>
          <div>
            <div className="muted small">Status</div>
            <OrderBadge status={event.status as never} />
          </div>
          <div>
            <div className="muted small">Product</div>
            <div className="strong">{event.item_name}</div>
          </div>
          <div>
            <div className="muted small">Kind</div>
            <div className="strong">
              {event.kind === 'ACTUAL' ? 'Already done' : event.kind === 'DUE' ? 'Customer promise' : 'Planned work'}
            </div>
          </div>
        </div>
        {event.detail && <div className="secondary">{event.detail}</div>}

        {event.kind === 'ACTUAL' && (
          <Alert tone="info">
            This is recorded history — {event.title}. Production that already happened cannot be
            re-planned, only corrected by booking against the order.
          </Alert>
        )}

        {editable && (
          <form id="cal-form" onSubmit={save} className="stack" style={{ gap: 12 }}>
            <label className="row tight" style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={moveDue}
                onChange={(e) => setMoveDue(e.target.checked)}
                style={{ width: 'auto' }}
              />
              <span className="small">Move the customer due date instead of the plan</span>
            </label>

            {moveDue ? (
              <>
                <Alert tone="info">
                  Changing a due date is a re-promise to the customer, not a re-plan. It is recorded
                  on the order with the reason you give.
                </Alert>
                <Field label="New due date">
                  <input
                    type="datetime-local"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                    required
                  />
                </Field>
                <Field label="Reason" note="required">
                  <input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Customer agreed a later date"
                    required
                  />
                </Field>
              </>
            ) : (
              <div className="row">
                <div style={{ flex: 1 }}>
                  <Field label="Planned start">
                    <input
                      type="datetime-local"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                      required
                    />
                  </Field>
                </div>
                <div style={{ flex: 1 }}>
                  <Field label="Planned end">
                    <input
                      type="datetime-local"
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                      required
                    />
                  </Field>
                </div>
              </div>
            )}
          </form>
        )}
      </div>
    </Modal>
  )
}
