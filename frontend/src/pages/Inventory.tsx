import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'

import { errorMessage } from '../api/client'
import {
  useAdjust,
  useGoodsReceipt,
  useItems,
  useLocations,
  useLots,
  useMovements,
  useOnHand,
  useTrace,
  useTransfer,
} from '../api/hooks'
import { Layout } from '../components/Layout'
import { Alert, Card, Empty, Field, Loading, LotBadge, Modal } from '../components/ui'
import { useAuth } from '../lib/auth'
import { dateTime, money, qty, titleCase } from '../lib/format'

type Tab = 'stock' | 'lots' | 'movements' | 'trace'

export function Inventory() {
  const { can } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>(searchParams.get('trace') ? 'trace' : 'stock')
  const [dialog, setDialog] = useState<'receipt' | 'transfer' | 'adjust' | null>(null)

  return (
    <Layout
      title="Inventory"
      subtitle="On-hand stock, lot detail, the movement ledger and lot genealogy"
      actions={
        can('WAREHOUSE', 'PLANNER') ? (
          <>
            <button onClick={() => setDialog('transfer')}>Transfer</button>
            <button onClick={() => setDialog('adjust')}>Adjust</button>
            <button className="primary" onClick={() => setDialog('receipt')}>
              + Goods receipt
            </button>
          </>
        ) : undefined
      }
    >
      <div className="tabs">
        {(['stock', 'lots', 'movements', 'trace'] as Tab[]).map((key) => (
          <button
            key={key}
            className={tab === key ? 'active' : ''}
            onClick={() => {
              setTab(key)
              if (key !== 'trace') setSearchParams({}, { replace: true })
            }}
          >
            {key === 'stock' ? 'On hand' : key === 'trace' ? 'Lot trace' : titleCase(key)}
          </button>
        ))}
      </div>

      {tab === 'stock' && <OnHandTable />}
      {tab === 'lots' && <LotsTable />}
      {tab === 'movements' && <MovementsTable />}
      {tab === 'trace' && (
        <TracePanel
          initial={searchParams.get('trace') ?? ''}
          onChange={(value) => setSearchParams(value ? { trace: value } : {}, { replace: true })}
        />
      )}

      {dialog === 'receipt' && <ReceiptModal onClose={() => setDialog(null)} />}
      {dialog === 'transfer' && <TransferModal onClose={() => setDialog(null)} />}
      {dialog === 'adjust' && <AdjustModal onClose={() => setDialog(null)} />}
    </Layout>
  )
}

function OnHandTable() {
  const [lowOnly, setLowOnly] = useState(false)
  const { data, isLoading } = useOnHand(lowOnly)
  if (isLoading) return <Loading />

  const totalValue = (data ?? []).reduce((sum, row) => sum + row.value, 0)

  return (
    <Card
      title="Stock on hand"
      hint={`${(data ?? []).length} parts · inventory value ${money(totalValue)}`}
      actions={
        <button className={lowOnly ? 'primary sm' : 'sm'} onClick={() => setLowOnly((value) => !value)}>
          {lowOnly ? 'Showing shortages' : 'Show shortages only'}
        </button>
      }
      flush
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Part</th>
              <th className="num">On hand</th>
              <th className="num">Safety stock</th>
              <th className="num">Lots</th>
              <th className="num">Value</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).length === 0 && (
              <tr>
                <td colSpan={6}>
                  <Empty>{lowOnly ? 'No parts are below safety stock' : 'No stock recorded'}</Empty>
                </td>
              </tr>
            )}
            {(data ?? []).map((row) => (
              <tr key={row.item_id}>
                <td>
                  <span className="code strong">{row.item_code}</span>
                  <div className="muted small">{row.item_name}</div>
                </td>
                <td className="num strong">
                  {qty(row.on_hand)} <span className="muted">{row.uom}</span>
                </td>
                <td className="num secondary">{qty(row.safety_stock)}</td>
                <td className="num secondary">{row.lot_count}</td>
                <td className="num secondary">{money(row.value)}</td>
                <td>
                  {row.below_safety_stock ? (
                    <span className="badge bad">
                      <span className="dot" /> Below safety
                    </span>
                  ) : (
                    <span className="badge good">
                      <span className="dot" /> OK
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function LotsTable() {
  const [search, setSearch] = useState('')
  const { data: locations } = useLocations()
  const [locationId, setLocationId] = useState<number | ''>('')
  const { data, isLoading } = useLots({
    lot_no: search || undefined,
    location_id: locationId === '' ? undefined : Number(locationId),
  })

  return (
    <Card
      title="Stock lots"
      hint="Every lot with quantity on hand"
      actions={
        <>
          <input
            placeholder="Filter by lot number"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ width: 190 }}
          />
          <select
            value={locationId}
            onChange={(event) => setLocationId(event.target.value === '' ? '' : Number(event.target.value))}
            style={{ width: 170 }}
          >
            <option value="">All locations</option>
            {(locations ?? []).map((location) => (
              <option key={location.id} value={location.id}>
                {location.code}
              </option>
            ))}
          </select>
        </>
      }
      flush
    >
      {isLoading ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Lot</th>
                <th>Part</th>
                <th>Location</th>
                <th className="num">Quantity</th>
                <th className="num">Unit cost</th>
                <th>Status</th>
                <th>Received</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <Empty>No lots match</Empty>
                  </td>
                </tr>
              )}
              {(data ?? []).map((lot) => (
                <tr key={lot.id}>
                  <td className="code strong">{lot.lot_no}</td>
                  <td>
                    <span className="code">{lot.item.code}</span>
                    <div className="muted small">{lot.item.name}</div>
                  </td>
                  <td>
                    <span className="code">{lot.location.code}</span>
                  </td>
                  <td className="num strong">
                    {qty(lot.qty)} <span className="muted">{lot.item.uom}</span>
                  </td>
                  <td className="num secondary">{money(lot.unit_cost)}</td>
                  <td>
                    <LotBadge status={lot.status} />
                  </td>
                  <td className="secondary small">{dateTime(lot.received_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function MovementsTable() {
  const [reference, setReference] = useState('')
  const { data, isLoading } = useMovements(reference ? { ref_no: reference } : undefined)

  return (
    <Card
      title="Movement ledger"
      hint="Append-only. Corrections are posted as new opposing movements, never edits."
      actions={
        <input
          placeholder="Filter by reference (WO-...)"
          value={reference}
          onChange={(event) => setReference(event.target.value)}
          style={{ width: 210 }}
        />
      }
      flush
    >
      {isLoading ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Type</th>
                <th>Part</th>
                <th>Lot</th>
                <th className="num">Quantity</th>
                <th>Reference</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <Empty>No movements match</Empty>
                  </td>
                </tr>
              )}
              {(data ?? []).map((movement) => (
                <tr key={movement.id}>
                  <td className="secondary small">{dateTime(movement.occurred_at)}</td>
                  <td>
                    <span className="badge info">{titleCase(movement.movement_type)}</span>
                  </td>
                  <td>
                    <span className="code">{movement.item.code}</span>
                  </td>
                  <td className="code small">{movement.lot_no ?? '-'}</td>
                  <td className="num strong">{qty(movement.qty)}</td>
                  <td className="code small">{movement.ref_no ?? '-'}</td>
                  <td className="muted small">{movement.note ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function TracePanel({ initial, onChange }: { initial: string; onChange: (value: string) => void }) {
  const [input, setInput] = useState(initial)
  const [lotNo, setLotNo] = useState(initial)
  const { data, isLoading, error } = useTrace(lotNo || null)

  function submit(event: FormEvent) {
    event.preventDefault()
    setLotNo(input.trim())
    onChange(input.trim())
  }

  return (
    <div className="stack">
      <Card title="Lot genealogy" hint="Where a lot is now, how it moved, and what went into it">
        <form className="row" onSubmit={submit}>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Enter or scan a lot number, e.g. LOT-2609-0007"
            style={{ flex: 1, minWidth: 220 }}
          />
          <button className="primary" type="submit">
            Trace
          </button>
        </form>
      </Card>

      {isLoading && <Loading />}
      {error && <Alert tone="error">{errorMessage(error, 'Lot not found')}</Alert>}

      {data && (
        <>
          <Card title="Current stock" hint={`Lot ${data.lot_no}`} flush>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Part</th>
                    <th>Location</th>
                    <th className="num">Quantity</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.current_stock.map((lot) => (
                    <tr key={lot.id}>
                      <td>
                        <span className="code">{lot.item.code}</span>{' '}
                        <span className="secondary">{lot.item.name}</span>
                      </td>
                      <td className="code">{lot.location.code}</td>
                      <td className="num strong">{qty(lot.qty)}</td>
                      <td>
                        <LotBadge status={lot.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card
            title="Components consumed"
            hint={
              data.source_order_id
                ? 'Material issued to the work order that produced this lot'
                : 'This lot was received, not produced'
            }
            flush
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Lot</th>
                    <th className="num">Quantity</th>
                    <th>Issued</th>
                  </tr>
                </thead>
                <tbody>
                  {data.consumed_components.length === 0 && (
                    <tr>
                      <td colSpan={4}>
                        <Empty>No component consumption recorded against this lot</Empty>
                      </td>
                    </tr>
                  )}
                  {data.consumed_components.map((component, index) => (
                    <tr key={`${component.item_code}-${component.lot_no}-${index}`}>
                      <td>
                        <span className="code">{component.item_code}</span>
                        <div className="muted small">{component.item_name}</div>
                      </td>
                      <td className="code small">{component.lot_no ?? '-'}</td>
                      <td className="num">{qty(component.qty)}</td>
                      <td className="secondary small">{dateTime(component.occurred_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Movement history" flush>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Type</th>
                    <th className="num">Quantity</th>
                    <th>Reference</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {data.movements.map((movement) => (
                    <tr key={movement.id}>
                      <td className="secondary small">{dateTime(movement.occurred_at)}</td>
                      <td>
                        <span className="badge info">{titleCase(movement.movement_type)}</span>
                      </td>
                      <td className="num">{qty(movement.qty)}</td>
                      <td className="code small">{movement.ref_no ?? '-'}</td>
                      <td className="muted small">{movement.note ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

function useItemOptions() {
  const { data } = useItems()
  return data ?? []
}

function ReceiptModal({ onClose }: { onClose: () => void }) {
  const items = useItemOptions()
  const { data: locations } = useLocations()
  const receipt = useGoodsReceipt()
  const [form, setForm] = useState({ item_id: '', qty: '', lot_no: '', location_id: '', unit_cost: '', note: '' })
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await receipt.mutateAsync({
        item_id: Number(form.item_id),
        qty: Number(form.qty),
        lot_no: form.lot_no || null,
        location_id: form.location_id ? Number(form.location_id) : null,
        unit_cost: form.unit_cost ? Number(form.unit_cost) : 0,
        note: form.note || null,
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title="Goods receipt"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="receipt-form" type="submit" disabled={receipt.isPending}>
            {receipt.isPending ? 'Booking...' : 'Book receipt'}
          </button>
        </>
      }
    >
      <form id="receipt-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Part">
          <select
            value={form.item_id}
            onChange={(event) => setForm({ ...form, item_id: event.target.value })}
            required
          >
            <option value="">Select a part...</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} - {item.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Quantity">
              <input
                type="number"
                step="0.001"
                min="0.001"
                value={form.qty}
                onChange={(event) => setForm({ ...form, qty: event.target.value })}
                required
              />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Unit cost" note="optional">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.unit_cost}
                onChange={(event) => setForm({ ...form, unit_cost: event.target.value })}
              />
            </Field>
          </div>
        </div>
        <Field label="Lot number" note="generated if left blank">
          <input value={form.lot_no} onChange={(event) => setForm({ ...form, lot_no: event.target.value })} />
        </Field>
        <Field label="Location" note="defaults to the raw store">
          <select
            value={form.location_id}
            onChange={(event) => setForm({ ...form, location_id: event.target.value })}
          >
            <option value="">Default raw store</option>
            {(locations ?? []).map((location) => (
              <option key={location.id} value={location.id}>
                {location.code} - {location.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Note" note="optional">
          <input value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
        </Field>
      </form>
    </Modal>
  )
}

function TransferModal({ onClose }: { onClose: () => void }) {
  const items = useItemOptions()
  const { data: locations } = useLocations()
  const transfer = useTransfer()
  const [form, setForm] = useState({ item_id: '', lot_no: '', from: '', to: '', qty: '', note: '' })
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await transfer.mutateAsync({
        item_id: Number(form.item_id),
        lot_no: form.lot_no,
        from_location_id: Number(form.from),
        to_location_id: Number(form.to),
        qty: Number(form.qty),
        note: form.note || null,
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title="Stock transfer"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="transfer-form" type="submit" disabled={transfer.isPending}>
            {transfer.isPending ? 'Moving...' : 'Transfer'}
          </button>
        </>
      }
    >
      <form id="transfer-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Part">
          <select value={form.item_id} onChange={(event) => setForm({ ...form, item_id: event.target.value })} required>
            <option value="">Select a part...</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} - {item.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Lot number">
          <input value={form.lot_no} onChange={(event) => setForm({ ...form, lot_no: event.target.value })} required />
        </Field>
        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="From">
              <select value={form.from} onChange={(event) => setForm({ ...form, from: event.target.value })} required>
                <option value="">Source...</option>
                {(locations ?? []).map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.code}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="To">
              <select value={form.to} onChange={(event) => setForm({ ...form, to: event.target.value })} required>
                <option value="">Destination...</option>
                {(locations ?? []).map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.code}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>
        <Field label="Quantity">
          <input
            type="number"
            step="0.001"
            min="0.001"
            value={form.qty}
            onChange={(event) => setForm({ ...form, qty: event.target.value })}
            required
          />
        </Field>
        <Field label="Note" note="optional">
          <input value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
        </Field>
      </form>
    </Modal>
  )
}

function AdjustModal({ onClose }: { onClose: () => void }) {
  const items = useItemOptions()
  const { data: locations } = useLocations()
  const adjust = useAdjust()
  const [form, setForm] = useState({ item_id: '', lot_no: '', location_id: '', qty: '', reason: '' })
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await adjust.mutateAsync({
        item_id: Number(form.item_id),
        lot_no: form.lot_no,
        location_id: Number(form.location_id),
        qty: Number(form.qty),
        reason: form.reason,
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title="Stock adjustment"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="adjust-form" type="submit" disabled={adjust.isPending}>
            {adjust.isPending ? 'Posting...' : 'Post adjustment'}
          </button>
        </>
      }
    >
      <form id="adjust-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Part">
          <select value={form.item_id} onChange={(event) => setForm({ ...form, item_id: event.target.value })} required>
            <option value="">Select a part...</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} - {item.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Lot number">
              <input value={form.lot_no} onChange={(event) => setForm({ ...form, lot_no: event.target.value })} required />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Location">
              <select
                value={form.location_id}
                onChange={(event) => setForm({ ...form, location_id: event.target.value })}
                required
              >
                <option value="">Select...</option>
                {(locations ?? []).map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.code}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>
        <Field label="Adjustment quantity" note="positive adds stock, negative writes it down">
          <input
            type="number"
            step="0.001"
            value={form.qty}
            onChange={(event) => setForm({ ...form, qty: event.target.value })}
            required
          />
        </Field>
        <Field label="Reason" note="recorded on the ledger entry">
          <input
            value={form.reason}
            onChange={(event) => setForm({ ...form, reason: event.target.value })}
            placeholder="Cycle count variance"
            required
          />
        </Field>
      </form>
    </Modal>
  )
}
