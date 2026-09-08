import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'

import { errorMessage } from '../api/client'
import {
  useConfirm,
  useDefectCodes,
  useMachines,
  useOrder,
  useScan,
  useWorkCenters,
  useWorkQueue,
} from '../api/hooks'
import type { OrderOperation } from '../api/types'
import { Layout } from '../components/Layout'
import { Alert, Card, Empty, Field, Loading, OperationBadge, OrderBadge } from '../components/ui'
import { useAuth } from '../lib/auth'
import { qty } from '../lib/format'

/**
 * Operator terminal.
 *
 * A shop-floor scanner behaves as a keyboard that types a code and presses
 * Enter, so the whole screen is driven from one always-focused input. The
 * backend resolves what a scanned code refers to (order, item, lot, badge).
 */
export function Terminal() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const [orderId, setOrderId] = useState<number | null>(null)
  const [operationId, setOperationId] = useState<number | null>(null)
  const [scanText, setScanText] = useState('')
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error' | 'info'; text: string } | null>(null)
  const [workCenterId, setWorkCenterId] = useState<number | ''>('')

  const scanInput = useRef<HTMLInputElement>(null)
  const scan = useScan()
  const { data: order, isLoading: loadingOrder } = useOrder(orderId)
  const { data: queue } = useWorkQueue(workCenterId === '' ? null : Number(workCenterId))
  const { data: workCenters } = useWorkCenters()

  const focusScanner = () => scanInput.current?.focus()
  useEffect(focusScanner, [orderId, operationId])

  // Deep link from the order screen: /terminal?order=WO-...
  const preset = searchParams.get('order')
  useEffect(() => {
    if (!preset) return
    scan.mutateAsync(preset).then((result) => {
      if (result.kind === 'ORDER' && result.id) setOrderId(result.id)
      setSearchParams({}, { replace: true })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset])

  async function handleScan(event: FormEvent) {
    event.preventDefault()
    const code = scanText.trim()
    if (!code) return
    setScanText('')
    setNotice(null)
    try {
      const result = await scan.mutateAsync(code)
      switch (result.kind) {
        case 'ORDER':
          setOrderId(result.id)
          setOperationId(null)
          setNotice({ tone: 'info', text: `Loaded ${result.label}` })
          break
        case 'BADGE':
          setNotice({ tone: 'info', text: `Badge recognised: ${result.label}` })
          break
        case 'ITEM':
        case 'LOT':
          setNotice({ tone: 'info', text: result.label })
          break
        default:
          setNotice({ tone: 'error', text: result.label })
      }
    } catch (exception) {
      setNotice({ tone: 'error', text: errorMessage(exception) })
    } finally {
      focusScanner()
    }
  }

  const operations = [...(order?.operations ?? [])].sort((a, b) => a.seq - b.seq)
  const selected = operations.find((operation) => operation.id === operationId) ?? null

  return (
    <Layout
      title="Shop floor terminal"
      subtitle={`Signed in as ${user?.full_name}${user?.badge_no ? ` · badge ${user.badge_no}` : ''}`}
    >
      <div className="terminal stack">
        <Card flush>
          <form className="scan-bar" onSubmit={handleScan}>
            <input
              ref={scanInput}
              value={scanText}
              onChange={(event) => setScanText(event.target.value)}
              placeholder="Scan a work order, part, lot or badge..."
              aria-label="Scan code"
              autoFocus
              autoComplete="off"
              spellCheck={false}
            />
            <button className="primary" type="submit" disabled={scan.isPending}>
              {scan.isPending ? 'Looking up...' : 'Look up'}
            </button>
            {order && (
              <button
                type="button"
                onClick={() => {
                  setOrderId(null)
                  setOperationId(null)
                  setNotice(null)
                }}
              >
                Clear
              </button>
            )}
          </form>
        </Card>

        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

        {loadingOrder && <Loading />}

        {!order && !loadingOrder && (
          <Card
            title="Work queue"
            hint="Released operations waiting to run, highest priority first"
            actions={
              <select
                value={workCenterId}
                onChange={(event) =>
                  setWorkCenterId(event.target.value === '' ? '' : Number(event.target.value))
                }
                style={{ width: 190 }}
              >
                <option value="">All work centres</option>
                {(workCenters ?? []).map((workCenter) => (
                  <option key={workCenter.id} value={workCenter.id}>
                    {workCenter.code} - {workCenter.name}
                  </option>
                ))}
              </select>
            }
            flush
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th className="num">Seq</th>
                    <th>Operation</th>
                    <th>Work centre</th>
                    <th className="num">Done</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(queue ?? []).length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        <Empty>Nothing queued. Scan a work order to begin.</Empty>
                      </td>
                    </tr>
                  )}
                  {(queue ?? []).map((operation) => (
                    <tr key={operation.id}>
                      <td className="num code">{operation.seq}</td>
                      <td className="strong">{operation.name}</td>
                      <td className="code">{operation.work_center.code}</td>
                      <td className="num">{qty(operation.qty_completed)}</td>
                      <td>
                        <OperationBadge status={operation.status} />
                      </td>
                      <td className="num">
                        <button
                          className="sm"
                          onClick={() => {
                            setOrderId(operation.order_id)
                            setOperationId(operation.id)
                          }}
                        >
                          Open
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {order && (
          <>
            <Card
              title={`${order.order_no} · ${order.item.name}`}
              hint={
                <>
                  {qty(order.qty_produced)} of {qty(order.qty_ordered)} {order.item.uom} produced
                  {order.output_lot_no && ` · output lot ${order.output_lot_no}`}
                </>
              }
              actions={<OrderBadge status={order.status} />}
            >
              <div className="op-grid">
                {operations.map((operation) => (
                  <button
                    key={operation.id}
                    className={`op-card${operation.id === operationId ? ' selected' : ''}`}
                    onClick={() => setOperationId(operation.id)}
                    disabled={operation.status === 'COMPLETED'}
                  >
                    <div className="seq">
                      OP {operation.seq} · {operation.work_center.code}
                    </div>
                    <div className="op-name">{operation.name}</div>
                    <div className="row tight" style={{ justifyContent: 'space-between' }}>
                      <OperationBadge status={operation.status} />
                      <span className="small secondary">
                        {qty(operation.qty_completed)} / {qty(order.qty_ordered)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </Card>

            {selected ? (
              <ConfirmPanel
                operation={selected}
                orderQty={order.qty_ordered}
                onDone={(message) => {
                  setNotice({ tone: 'ok', text: message })
                  focusScanner()
                }}
                onError={(message) => setNotice({ tone: 'error', text: message })}
              />
            ) : (
              <Card>
                <Empty>Select an operation above to report production.</Empty>
              </Card>
            )}
          </>
        )}
      </div>
    </Layout>
  )
}

function ConfirmPanel({
  operation,
  orderQty,
  onDone,
  onError,
}: {
  operation: OrderOperation
  orderQty: number
  onDone: (message: string) => void
  onError: (message: string) => void
}) {
  const confirm = useConfirm()
  const { data: machines } = useMachines()
  const { data: defects } = useDefectCodes()

  const [good, setGood] = useState('')
  const [scrap, setScrap] = useState('')
  const [defectId, setDefectId] = useState<number | ''>('')
  const [machineId, setMachineId] = useState<number | ''>('')
  const [note, setNote] = useState('')

  const remaining = Math.max(orderQty - operation.qty_completed - operation.qty_scrapped, 0)
  const eligibleMachines = (machines ?? []).filter(
    (machine) => machine.work_center_id === operation.work_center_id,
  )

  // Default to the single machine at this work centre; reset when the step changes.
  useEffect(() => {
    setGood('')
    setScrap('')
    setDefectId('')
    setNote('')
    setMachineId(eligibleMachines.length === 1 ? eligibleMachines[0].id : '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operation.id, machines])

  const scrapQty = Number(scrap || 0)

  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      await confirm.mutateAsync({
        operation_id: operation.id,
        qty_good: Number(good || 0),
        qty_scrap: scrapQty,
        defect_code_id: defectId === '' ? null : Number(defectId),
        machine_id: machineId === '' ? null : Number(machineId),
        note: note || null,
      })
      onDone(`Booked ${good || 0} good${scrapQty ? ` and ${scrapQty} scrap` : ''} on OP ${operation.seq}.`)
      setGood('')
      setScrap('')
      setDefectId('')
      setNote('')
    } catch (exception) {
      onError(errorMessage(exception))
    }
  }

  return (
    <Card
      title={`Report OP ${operation.seq} · ${operation.name}`}
      hint={
        <>
          {qty(remaining)} still to run at {operation.work_center.name}
          {operation.requires_inspection && ' · output is held for inspection'}
        </>
      }
    >
      {operation.instructions && (
        <div className="alert info" style={{ marginBottom: 14 }}>
          <span className="icon" aria-hidden="true">
            i
          </span>
          <div>{operation.instructions}</div>
        </div>
      )}

      <form onSubmit={submit} className="stack" style={{ gap: 14 }}>
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 130 }} className="big-input">
            <Field label="Good quantity">
              <input
                type="number"
                min="0"
                step="1"
                value={good}
                onChange={(event) => setGood(event.target.value)}
                placeholder="0"
                autoFocus
              />
            </Field>
          </div>
          <div style={{ flex: 1, minWidth: 130 }} className="big-input">
            <Field label="Scrap quantity">
              <input
                type="number"
                min="0"
                step="1"
                value={scrap}
                onChange={(event) => setScrap(event.target.value)}
                placeholder="0"
              />
            </Field>
          </div>
          <div style={{ flex: 1, minWidth: 160, paddingTop: 22 }}>
            <button
              type="button"
              onClick={() => setGood(String(remaining))}
              disabled={remaining <= 0}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              All remaining ({qty(remaining)})
            </button>
          </div>
        </div>

        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 190 }}>
            <Field label="Machine">
              <select
                value={machineId}
                onChange={(event) => setMachineId(event.target.value === '' ? '' : Number(event.target.value))}
              >
                <option value="">Not recorded</option>
                {eligibleMachines.map((machine) => (
                  <option key={machine.id} value={machine.id}>
                    {machine.code} - {machine.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div style={{ flex: 1, minWidth: 190 }}>
            <Field label="Defect code" note={scrapQty > 0 ? 'required for scrap' : 'optional'}>
              <select
                value={defectId}
                onChange={(event) => setDefectId(event.target.value === '' ? '' : Number(event.target.value))}
                required={scrapQty > 0}
                disabled={scrapQty <= 0}
              >
                <option value="">Select...</option>
                {(defects ?? []).map((defect) => (
                  <option key={defect.id} value={defect.id}>
                    {defect.code} - {defect.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>

        <Field label="Note" note="optional">
          <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Anything the next shift should know" />
        </Field>

        <div className="row">
          <button
            className="primary"
            type="submit"
            disabled={confirm.isPending || (!Number(good) && !scrapQty)}
            style={{ padding: '10px 20px', fontSize: 14 }}
          >
            {confirm.isPending ? 'Booking...' : 'Confirm production'}
          </button>
          <span className="muted small">
            Recording {good || 0} good{scrapQty ? ` and ${scrapQty} scrap` : ''} against OP {operation.seq}
          </span>
        </div>
      </form>
    </Card>
  )
}
