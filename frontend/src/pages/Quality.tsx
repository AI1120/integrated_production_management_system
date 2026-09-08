import { useState, type FormEvent } from 'react'

import { errorMessage } from '../api/client'
import {
  useInspectionPlans,
  useInspections,
  useItems,
  useLots,
  useNcrs,
  useRecordInspection,
  useUpdateNcr,
} from '../api/hooks'
import type { Disposition, Inspection, InspectionPlan, NcrStatus } from '../api/types'
import { Layout } from '../components/Layout'
import {
  Alert,
  Card,
  Empty,
  Field,
  JudgmentBadge,
  Loading,
  Modal,
  NcrBadge,
} from '../components/ui'
import { useAuth } from '../lib/auth'
import { dateTime, qty, titleCase } from '../lib/format'

type Tab = 'inspections' | 'ncrs' | 'plans'

const DISPOSITIONS: Disposition[] = ['PENDING', 'REWORK', 'SCRAP', 'USE_AS_IS', 'RETURN_TO_SUPPLIER']
const NCR_STATUSES: NcrStatus[] = ['OPEN', 'IN_REVIEW', 'CLOSED']

export function Quality() {
  const { can } = useAuth()
  const [tab, setTab] = useState<Tab>('inspections')
  const [recording, setRecording] = useState(false)

  return (
    <Layout
      title="Quality"
      subtitle="Inspections, measured results and non-conformance handling"
      actions={
        can('QC') ? (
          <button className="primary" onClick={() => setRecording(true)}>
            + Record inspection
          </button>
        ) : undefined
      }
    >
      <div className="tabs">
        {(['inspections', 'ncrs', 'plans'] as Tab[]).map((key) => (
          <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
            {key === 'ncrs' ? 'Non-conformance' : titleCase(key)}
          </button>
        ))}
      </div>

      {tab === 'inspections' && <InspectionsTable />}
      {tab === 'ncrs' && <NcrTable />}
      {tab === 'plans' && <PlansTable />}

      {recording && <RecordInspectionModal onClose={() => setRecording(false)} />}
    </Layout>
  )
}

function InspectionsTable() {
  const { data, isLoading } = useInspections()
  const [open, setOpen] = useState<Inspection | null>(null)
  if (isLoading) return <Loading />

  return (
    <>
      <Card title="Inspections" hint="A failure blocks the lot and raises an NCR automatically" flush>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Number</th>
                <th>Type</th>
                <th>Part</th>
                <th>Lot</th>
                <th className="num">Inspected</th>
                <th className="num">Rejected</th>
                <th>Result</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <Empty>No inspections recorded</Empty>
                  </td>
                </tr>
              )}
              {(data ?? []).map((inspection) => (
                <tr key={inspection.id} className="clickable" onClick={() => setOpen(inspection)}>
                  <td className="code strong">{inspection.inspection_no}</td>
                  <td className="secondary">{titleCase(inspection.inspection_type)}</td>
                  <td>
                    <span className="code">{inspection.item.code}</span>
                    <div className="muted small">{inspection.item.name}</div>
                  </td>
                  <td className="code small">{inspection.lot_no ?? '-'}</td>
                  <td className="num">{qty(inspection.qty_inspected)}</td>
                  <td className="num">{inspection.qty_rejected ? qty(inspection.qty_rejected) : '-'}</td>
                  <td>
                    <JudgmentBadge result={inspection.result} />
                  </td>
                  <td className="secondary small">{dateTime(inspection.inspected_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {open && (
        <Modal
          title={`${open.inspection_no} · ${open.item.code}`}
          onClose={() => setOpen(null)}
          footer={<button onClick={() => setOpen(null)}>Close</button>}
        >
          <div className="stack" style={{ gap: 14 }}>
            <div className="row" style={{ gap: 20 }}>
              <div>
                <div className="muted small">Result</div>
                <JudgmentBadge result={open.result} />
              </div>
              <div>
                <div className="muted small">Lot</div>
                <div className="code">{open.lot_no ?? '-'}</div>
              </div>
              <div>
                <div className="muted small">Accepted / rejected</div>
                <div className="strong">
                  {qty(open.qty_accepted)} / {qty(open.qty_rejected)}
                </div>
              </div>
            </div>

            {open.results.length === 0 ? (
              <Empty>No individual measurements were recorded</Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Characteristic</th>
                      <th className="num">Sample</th>
                      <th className="num">Value</th>
                      <th>Judgment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {open.results.map((result) => (
                      <tr key={result.id}>
                        <td>{result.characteristic_name}</td>
                        <td className="num secondary">{result.sample_no}</td>
                        <td className="num strong">
                          {result.value_numeric ?? result.value_text ?? '-'}
                        </td>
                        <td>
                          <JudgmentBadge result={result.judgment} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {open.note && <div className="secondary small">{open.note}</div>}
          </div>
        </Modal>
      )}
    </>
  )
}

function NcrTable() {
  const [filter, setFilter] = useState<NcrStatus | ''>('')
  const { data, isLoading } = useNcrs(filter || undefined)
  const update = useUpdateNcr()
  const { can } = useAuth()
  const [error, setError] = useState<string | null>(null)

  if (isLoading) return <Loading />

  async function change(id: number, body: Record<string, unknown>) {
    setError(null)
    try {
      await update.mutateAsync({ id, body })
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <div className="stack">
      {error && <Alert tone="error">{error}</Alert>}
      <Card
        title="Non-conformance reports"
        hint="Setting the disposition to Scrap writes the quantity off stock immediately"
        actions={
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as NcrStatus | '')}
            style={{ width: 150 }}
          >
            <option value="">All statuses</option>
            {NCR_STATUSES.map((status) => (
              <option key={status} value={status}>
                {titleCase(status)}
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
                <th>Number</th>
                <th>Part</th>
                <th>Lot</th>
                <th className="num">Qty</th>
                <th>Defect</th>
                <th>Disposition</th>
                <th>Status</th>
                <th>Raised</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <Empty>No non-conformances</Empty>
                  </td>
                </tr>
              )}
              {(data ?? []).map((ncr) => (
                <tr key={ncr.id}>
                  <td className="code strong">{ncr.ncr_no}</td>
                  <td>
                    <span className="code">{ncr.item.code}</span>
                    <div className="muted small">{ncr.item.name}</div>
                  </td>
                  <td className="code small">{ncr.lot_no ?? '-'}</td>
                  <td className="num">{qty(ncr.qty)}</td>
                  <td className="secondary small">
                    {ncr.defect_code ? `${ncr.defect_code.code} · ${ncr.defect_code.name}` : '-'}
                  </td>
                  <td>
                    {can('QC') ? (
                      <select
                        value={ncr.disposition}
                        onChange={(event) => change(ncr.id, { disposition: event.target.value })}
                        style={{ width: 165 }}
                        disabled={ncr.status === 'CLOSED'}
                      >
                        {DISPOSITIONS.map((disposition) => (
                          <option key={disposition} value={disposition}>
                            {titleCase(disposition)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      titleCase(ncr.disposition)
                    )}
                  </td>
                  <td>
                    {can('QC') ? (
                      <select
                        value={ncr.status}
                        onChange={(event) => change(ncr.id, { status: event.target.value })}
                        style={{ width: 130 }}
                      >
                        {NCR_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {titleCase(status)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <NcrBadge status={ncr.status} />
                    )}
                  </td>
                  <td className="secondary small">{dateTime(ncr.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function PlansTable() {
  const { data, isLoading } = useInspectionPlans()
  if (isLoading) return <Loading />

  return (
    <div className="stack">
      {(data ?? []).length === 0 && (
        <Card>
          <Empty>No inspection plans defined</Empty>
        </Card>
      )}
      {(data ?? []).map((plan) => (
        <Card
          key={plan.id}
          title={`${plan.code} · ${plan.name}`}
          hint={`${titleCase(plan.inspection_type)} inspection${
            plan.operation_seq ? ` at operation ${plan.operation_seq}` : ''
          } · sample size ${plan.sample_size}`}
          flush
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Seq</th>
                  <th>Characteristic</th>
                  <th>Type</th>
                  <th className="num">Target</th>
                  <th className="num">Lower</th>
                  <th className="num">Upper</th>
                  <th>Method</th>
                </tr>
              </thead>
              <tbody>
                {plan.characteristics.map((characteristic) => (
                  <tr key={characteristic.id}>
                    <td className="num code">{characteristic.seq}</td>
                    <td className="strong">
                      {characteristic.name}
                      {characteristic.uom && <span className="muted"> ({characteristic.uom})</span>}
                    </td>
                    <td className="secondary">{titleCase(characteristic.char_type)}</td>
                    <td className="num">{characteristic.target ?? '-'}</td>
                    <td className="num">{characteristic.lower_limit ?? '-'}</td>
                    <td className="num">{characteristic.upper_limit ?? '-'}</td>
                    <td className="secondary small">{characteristic.method ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </div>
  )
}

function RecordInspectionModal({ onClose }: { onClose: () => void }) {
  const { data: items } = useItems()
  const record = useRecordInspection()
  const [itemId, setItemId] = useState<number | ''>('')
  const { data: plans } = useInspectionPlans(itemId === '' ? undefined : Number(itemId))
  const { data: lots } = useLots({ item_id: itemId === '' ? undefined : Number(itemId) })

  const [planId, setPlanId] = useState<number | ''>('')
  const [lotNo, setLotNo] = useState('')
  const [inspected, setInspected] = useState('5')
  const [rejected, setRejected] = useState('0')
  const [note, setNote] = useState('')
  const [values, setValues] = useState<Record<number, string>>({})
  const [error, setError] = useState<string | null>(null)

  const plan: InspectionPlan | undefined = (plans ?? []).find((candidate) => candidate.id === planId)
  const quarantined = (lots ?? []).filter((lot) => lot.status === 'QUARANTINE')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await record.mutateAsync({
        item_id: Number(itemId),
        plan_id: planId === '' ? null : Number(planId),
        inspection_type: plan?.inspection_type ?? 'FINAL',
        lot_no: lotNo || null,
        qty_inspected: Number(inspected),
        qty_rejected: Number(rejected || 0),
        note: note || null,
        results: (plan?.characteristics ?? [])
          .filter((characteristic) => (values[characteristic.id] ?? '').trim() !== '')
          .map((characteristic) => ({
            characteristic_id: characteristic.id,
            characteristic_name: characteristic.name,
            sample_no: 1,
            value_numeric:
              characteristic.char_type === 'NUMERIC' ? Number(values[characteristic.id]) : null,
            value_text: characteristic.char_type === 'ATTRIBUTE' ? values[characteristic.id] : null,
          })),
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title="Record inspection"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="inspection-form" type="submit" disabled={!itemId || record.isPending}>
            {record.isPending ? 'Recording...' : 'Record inspection'}
          </button>
        </>
      }
    >
      <form id="inspection-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}

        <Field label="Part">
          <select
            value={itemId}
            onChange={(event) => {
              setItemId(Number(event.target.value))
              setPlanId('')
              setLotNo('')
              setValues({})
            }}
            required
          >
            <option value="">Select a part...</option>
            {(items ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} - {item.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Lot" note="lots awaiting inspection appear first">
          <select value={lotNo} onChange={(event) => setLotNo(event.target.value)}>
            <option value="">No specific lot</option>
            {quarantined.map((lot) => (
              <option key={lot.id} value={lot.lot_no}>
                {lot.lot_no} · {qty(lot.qty)} in {lot.location.code} (quarantine)
              </option>
            ))}
            {(lots ?? [])
              .filter((lot) => lot.status !== 'QUARANTINE')
              .map((lot) => (
                <option key={lot.id} value={lot.lot_no}>
                  {lot.lot_no} · {qty(lot.qty)} in {lot.location.code}
                </option>
              ))}
          </select>
        </Field>

        <Field label="Inspection plan" note="optional - drives the measurement list">
          <select
            value={planId}
            onChange={(event) => setPlanId(event.target.value === '' ? '' : Number(event.target.value))}
          >
            <option value="">No plan</option>
            {(plans ?? []).map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.code} - {candidate.name}
              </option>
            ))}
          </select>
        </Field>

        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Quantity inspected">
              <input
                type="number"
                min="1"
                value={inspected}
                onChange={(event) => setInspected(event.target.value)}
                required
              />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Quantity rejected">
              <input type="number" min="0" value={rejected} onChange={(event) => setRejected(event.target.value)} />
            </Field>
          </div>
        </div>

        {plan && plan.characteristics.length > 0 && (
          <div>
            <div className="muted small" style={{ marginBottom: 8 }}>
              Measurements — values outside the limits automatically fail the inspection
            </div>
            <div className="stack" style={{ gap: 8 }}>
              {plan.characteristics.map((characteristic) => (
                <Field
                  key={characteristic.id}
                  label={`${characteristic.name}${characteristic.uom ? ` (${characteristic.uom})` : ''}`}
                  note={
                    characteristic.char_type === 'NUMERIC'
                      ? `limits ${characteristic.lower_limit ?? '-'} to ${characteristic.upper_limit ?? '-'}`
                      : 'enter OK or the defect seen'
                  }
                >
                  <input
                    type={characteristic.char_type === 'NUMERIC' ? 'number' : 'text'}
                    step="any"
                    value={values[characteristic.id] ?? ''}
                    onChange={(event) =>
                      setValues({ ...values, [characteristic.id]: event.target.value })
                    }
                    placeholder={
                      characteristic.char_type === 'NUMERIC'
                        ? String(characteristic.target ?? '')
                        : 'OK'
                    }
                  />
                </Field>
              ))}
            </div>
          </div>
        )}

        <Field label="Note" note="optional">
          <input value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
      </form>
    </Modal>
  )
}
