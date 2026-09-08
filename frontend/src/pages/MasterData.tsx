import { useState, type FormEvent } from 'react'

import { errorMessage } from '../api/client'
import {
  useBoms,
  useCreateItem,
  useDefectCodes,
  useItems,
  useLocations,
  useRoutings,
  useWorkCenters,
} from '../api/hooks'
import type { ItemType } from '../api/types'
import { Layout } from '../components/Layout'
import { Alert, Card, Empty, Field, Loading, Modal } from '../components/ui'
import { useAuth } from '../lib/auth'
import { money, qty, titleCase } from '../lib/format'

type Tab = 'items' | 'boms' | 'routings' | 'resources'

const ITEM_TYPES: ItemType[] = ['FINISHED_GOOD', 'SUB_ASSEMBLY', 'RAW_MATERIAL', 'CONSUMABLE']

export function MasterData() {
  const { can } = useAuth()
  const [tab, setTab] = useState<Tab>('items')
  const [creating, setCreating] = useState(false)

  return (
    <Layout
      title="Master data"
      subtitle="The definitions everything else in the plant is built on"
      actions={
        can('PLANNER') && tab === 'items' ? (
          <button className="primary" onClick={() => setCreating(true)}>
            + New part
          </button>
        ) : undefined
      }
    >
      <div className="tabs">
        {(['items', 'boms', 'routings', 'resources'] as Tab[]).map((key) => (
          <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
            {key === 'boms' ? 'Bills of material' : titleCase(key)}
          </button>
        ))}
      </div>

      {tab === 'items' && <ItemsTable />}
      {tab === 'boms' && <BomList />}
      {tab === 'routings' && <RoutingList />}
      {tab === 'resources' && <Resources />}

      {creating && <NewItemModal onClose={() => setCreating(false)} />}
    </Layout>
  )
}

function ItemsTable() {
  const [search, setSearch] = useState('')
  const [type, setType] = useState<ItemType | ''>('')
  const { data, isLoading } = useItems({
    q: search || undefined,
    item_type: type || undefined,
  })

  return (
    <Card
      title="Part master"
      hint="Everything that can be made, bought or stocked"
      actions={
        <>
          <input
            placeholder="Search code or name"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ width: 190 }}
          />
          <select
            value={type}
            onChange={(event) => setType(event.target.value as ItemType | '')}
            style={{ width: 165 }}
          >
            <option value="">All types</option>
            {ITEM_TYPES.map((value) => (
              <option key={value} value={value}>
                {titleCase(value)}
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
                <th>Code</th>
                <th>Name</th>
                <th>Type</th>
                <th>UoM</th>
                <th className="num">Std cost</th>
                <th className="num">On hand</th>
                <th className="num">Safety</th>
                <th className="num">Lead time</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <Empty>No parts match</Empty>
                  </td>
                </tr>
              )}
              {(data ?? []).map((item) => (
                <tr key={item.id}>
                  <td className="code strong">{item.code}</td>
                  <td>{item.name}</td>
                  <td className="secondary">{titleCase(item.item_type)}</td>
                  <td className="secondary">{item.uom}</td>
                  <td className="num secondary">{money(item.standard_cost)}</td>
                  <td className="num strong" style={item.below_safety_stock ? { color: 'var(--critical)' } : undefined}>
                    {qty(item.on_hand ?? 0)}
                  </td>
                  <td className="num secondary">{qty(item.safety_stock)}</td>
                  <td className="num secondary">{item.lead_time_days ? `${item.lead_time_days}d` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function BomList() {
  const { data, isLoading } = useBoms()
  if (isLoading) return <Loading />

  return (
    <div className="stack">
      {(data ?? []).length === 0 && (
        <Card>
          <Empty>No bills of material defined</Empty>
        </Card>
      )}
      {(data ?? []).map((bom) => (
        <Card
          key={bom.id}
          title={`${bom.item.code} · ${bom.item.name}`}
          hint={`Version ${bom.version}${bom.is_active ? ' · active' : ' · inactive'} · ${bom.lines.length} components`}
          flush
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Line</th>
                  <th>Component</th>
                  <th className="num">Qty per</th>
                  <th className="num">Scrap %</th>
                  <th className="num">At operation</th>
                </tr>
              </thead>
              <tbody>
                {bom.lines.map((line) => (
                  <tr key={line.id}>
                    <td className="num code">{line.line_no}</td>
                    <td>
                      <span className="code strong">{line.component.code}</span>
                      <div className="muted small">{line.component.name}</div>
                    </td>
                    <td className="num">
                      {qty(line.qty_per)} <span className="muted">{line.component.uom}</span>
                    </td>
                    <td className="num secondary">{line.scrap_pct ? `${line.scrap_pct}%` : '-'}</td>
                    <td className="num secondary">{line.operation_seq ?? '-'}</td>
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

function RoutingList() {
  const { data, isLoading } = useRoutings()
  if (isLoading) return <Loading />

  return (
    <div className="stack">
      {(data ?? []).length === 0 && (
        <Card>
          <Empty>No routings defined</Empty>
        </Card>
      )}
      {(data ?? []).map((routing) => (
        <Card
          key={routing.id}
          title={`${routing.item.code} · ${routing.item.name}`}
          hint={`Version ${routing.version}${routing.is_active ? ' · active' : ' · inactive'} · ${
            routing.operations.length
          } operations`}
          flush
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Seq</th>
                  <th>Operation</th>
                  <th>Work centre</th>
                  <th className="num">Setup</th>
                  <th className="num">Run / unit</th>
                  <th>QC</th>
                  <th>Instructions</th>
                </tr>
              </thead>
              <tbody>
                {routing.operations.map((operation) => (
                  <tr key={operation.id}>
                    <td className="num code">{operation.seq}</td>
                    <td className="strong">{operation.name}</td>
                    <td>
                      <span className="code">{operation.work_center.code}</span>
                      <div className="muted small">{operation.work_center.name}</div>
                    </td>
                    <td className="num secondary">{operation.setup_minutes} min</td>
                    <td className="num secondary">{operation.run_minutes_per_unit} min</td>
                    <td>{operation.requires_inspection ? 'Required' : <span className="muted">-</span>}</td>
                    <td className="muted small">{operation.instructions ?? '-'}</td>
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

function Resources() {
  const { data: workCenters } = useWorkCenters()
  const { data: locations } = useLocations()
  const { data: defects } = useDefectCodes()

  return (
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
      <Card title="Work centres" flush>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th className="num">Cap / hr</th>
                <th className="num">Rate</th>
              </tr>
            </thead>
            <tbody>
              {(workCenters ?? []).map((workCenter) => (
                <tr key={workCenter.id}>
                  <td className="code strong">{workCenter.code}</td>
                  <td>{workCenter.name}</td>
                  <td className="num secondary">{workCenter.capacity_per_hour}</td>
                  <td className="num secondary">{money(workCenter.cost_rate_per_hour)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Stock locations" flush>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {(locations ?? []).map((location) => (
                <tr key={location.id}>
                  <td className="code strong">{location.code}</td>
                  <td>{location.name}</td>
                  <td className="secondary">{titleCase(location.location_type)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Defect codes" flush>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Category</th>
              </tr>
            </thead>
            <tbody>
              {(defects ?? []).map((defect) => (
                <tr key={defect.id}>
                  <td className="code strong">{defect.code}</td>
                  <td>{defect.name}</td>
                  <td className="secondary">{titleCase(defect.category)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function NewItemModal({ onClose }: { onClose: () => void }) {
  const create = useCreateItem()
  const [form, setForm] = useState({
    code: '',
    name: '',
    item_type: 'RAW_MATERIAL' as ItemType,
    uom: 'EA',
    standard_cost: '0',
    safety_stock: '0',
    lead_time_days: '0',
  })
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await create.mutateAsync({
        ...form,
        standard_cost: Number(form.standard_cost),
        safety_stock: Number(form.safety_stock),
        lead_time_days: Number(form.lead_time_days),
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title="New part"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="item-form" type="submit" disabled={create.isPending}>
            {create.isPending ? 'Creating...' : 'Create part'}
          </button>
        </>
      }
    >
      <form id="item-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Code">
              <input
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
                required
                autoFocus
              />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Unit of measure">
              <input value={form.uom} onChange={(event) => setForm({ ...form, uom: event.target.value })} required />
            </Field>
          </div>
        </div>
        <Field label="Name">
          <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
        </Field>
        <Field label="Type">
          <select
            value={form.item_type}
            onChange={(event) => setForm({ ...form, item_type: event.target.value as ItemType })}
          >
            {ITEM_TYPES.map((value) => (
              <option key={value} value={value}>
                {titleCase(value)}
              </option>
            ))}
          </select>
        </Field>
        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Standard cost">
              <input
                type="number"
                step="0.01"
                value={form.standard_cost}
                onChange={(event) => setForm({ ...form, standard_cost: event.target.value })}
              />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Safety stock">
              <input
                type="number"
                step="0.001"
                value={form.safety_stock}
                onChange={(event) => setForm({ ...form, safety_stock: event.target.value })}
              />
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Lead time" note="days">
              <input
                type="number"
                value={form.lead_time_days}
                onChange={(event) => setForm({ ...form, lead_time_days: event.target.value })}
              />
            </Field>
          </div>
        </div>
      </form>
    </Modal>
  )
}
