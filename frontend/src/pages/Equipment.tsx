import { useState, type FormEvent } from 'react'

import { errorMessage } from '../api/client'
import {
  useCloseMaintenance,
  useCreateMaintenance,
  useDowntime,
  useDowntimeReasons,
  useEndDowntime,
  useMachines,
  useMaintenance,
  useOee,
  useSetMachineStatus,
} from '../api/hooks'
import type { Machine, MachineStatus } from '../api/types'
import { OeeFactors } from '../components/charts'
import { Layout } from '../components/Layout'
import { Alert, Card, Empty, Field, Loading, MachineBadge, Meter, Modal } from '../components/ui'
import { useAuth } from '../lib/auth'
import { dateTime, duration, pct, qty, since, titleCase } from '../lib/format'

const OEE_TARGET = 0.85
const STATUSES: MachineStatus[] = ['IDLE', 'SETUP', 'RUNNING', 'DOWN', 'MAINTENANCE']

function tone(value: number): 'good' | 'warn' | 'bad' {
  if (value >= OEE_TARGET) return 'good'
  if (value >= 0.6) return 'warn'
  return 'bad'
}

export function Equipment() {
  const { can } = useAuth()
  const [days, setDays] = useState(1)
  const { data: machines, isLoading } = useMachines()
  const { data: oee } = useOee(days)
  const { data: openDowntime } = useDowntime({ open_only: true, days: 30 })
  const [stopping, setStopping] = useState<Machine | null>(null)
  const [requesting, setRequesting] = useState<Machine | null>(null)
  const [error, setError] = useState<string | null>(null)

  const setStatus = useSetMachineStatus()
  const endDowntime = useEndDowntime()

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  if (isLoading) {
    return (
      <Layout title="Equipment">
        <Loading />
      </Layout>
    )
  }

  const oeeByMachine = new Map((oee ?? []).map((row) => [row.machine_id, row]))

  return (
    <Layout
      title="Equipment & OEE"
      subtitle="Machine state, downtime capture and the loss analysis derived from it"
      actions={
        <select value={days} onChange={(event) => setDays(Number(event.target.value))} style={{ width: 150 }}>
          <option value={1}>Last 24 hours</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
        </select>
      }
    >
      <div className="stack">
        {error && <Alert tone="error">{error}</Alert>}

        <Card title="Machine board" hint="Stopping a machine opens a downtime event; restarting closes it" flush>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Machine</th>
                  <th>Work centre</th>
                  <th>State</th>
                  <th>Since</th>
                  <th className="num">Ideal cycle</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {(machines ?? []).map((machine) => {
                  const openEvent = (openDowntime ?? []).find((event) => event.machine_id === machine.id)
                  return (
                    <tr key={machine.id}>
                      <td>
                        <span className="code strong">{machine.code}</span>
                        <div className="muted small">{machine.name}</div>
                      </td>
                      <td className="code">{machine.work_center.code}</td>
                      <td>
                        <MachineBadge status={machine.status} />
                        {openEvent && (
                          <div className="muted small" style={{ marginTop: 3 }}>
                            {openEvent.reason.name}
                          </div>
                        )}
                      </td>
                      <td className="secondary small">{since(machine.status_since)}</td>
                      <td className="num secondary">{machine.ideal_cycle_seconds}s</td>
                      <td>
                        {can('OPERATOR', 'PLANNER') && (
                          <div className="row tight">
                            {machine.status === 'DOWN' || machine.status === 'MAINTENANCE' ? (
                              <button
                                className="sm primary"
                                onClick={() =>
                                  run(async () => {
                                    if (openEvent) await endDowntime.mutateAsync(openEvent.id)
                                    else await setStatus.mutateAsync({ id: machine.id, status: 'IDLE' })
                                  })
                                }
                              >
                                Restart
                              </button>
                            ) : (
                              <>
                                <button className="sm" onClick={() => setStopping(machine)}>
                                  Stop
                                </button>
                                {machine.status !== 'RUNNING' && (
                                  <button
                                    className="sm"
                                    onClick={() => run(() => setStatus.mutateAsync({ id: machine.id, status: 'RUNNING' }))}
                                  >
                                    Run
                                  </button>
                                )}
                              </>
                            )}
                            <button className="sm ghost" onClick={() => setRequesting(machine)}>
                              Maintenance
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          title="OEE factors"
          hint="Availability x Performance x Quality. The table below carries the exact figures."
        >
          <OeeFactors
            data={(oee ?? []).map((row) => ({
              machine: row.machine_code,
              availability: row.availability,
              performance: row.performance,
              quality: row.quality,
            }))}
          />
        </Card>

        <Card title="OEE detail" hint={`Window: last ${days === 1 ? '24 hours' : `${days} days`}`} flush>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Machine</th>
                  <th className="num">Loading</th>
                  <th className="num">Run</th>
                  <th className="num">Down</th>
                  <th className="num">Good</th>
                  <th className="num">Scrap</th>
                  <th className="num">A</th>
                  <th className="num">P</th>
                  <th className="num">Q</th>
                  <th className="num">OEE</th>
                  <th style={{ width: 110 }} />
                </tr>
              </thead>
              <tbody>
                {(machines ?? []).map((machine) => {
                  const row = oeeByMachine.get(machine.id)
                  if (!row) return null
                  return (
                    <tr key={machine.id}>
                      <td className="code strong">{machine.code}</td>
                      <td className="num secondary">{duration(row.loading_minutes)}</td>
                      <td className="num secondary">{duration(row.run_minutes)}</td>
                      <td className="num secondary">{duration(row.unplanned_downtime_minutes)}</td>
                      <td className="num">{qty(row.good_count)}</td>
                      <td className="num">{row.scrap_count ? qty(row.scrap_count) : '-'}</td>
                      <td className="num">{pct(row.availability, 0)}</td>
                      <td className="num">{pct(row.performance, 0)}</td>
                      <td className="num">{pct(row.quality, 0)}</td>
                      <td className="num strong">{pct(row.oee, 1)}</td>
                      <td>
                        <Meter value={row.oee} tone={tone(row.oee)} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.3fr) minmax(0, 1fr)' }}>
          <DowntimeLog />
          <MaintenanceList />
        </div>
      </div>

      {stopping && <StopModal machine={stopping} onClose={() => setStopping(null)} />}
      {requesting && <MaintenanceModal machine={requesting} onClose={() => setRequesting(null)} />}
    </Layout>
  )
}

function DowntimeLog() {
  const { data, isLoading } = useDowntime({ days: 7 })
  if (isLoading) return <Loading />

  return (
    <Card title="Downtime log" hint="Last 7 days" flush>
      <div className="table-wrap" style={{ maxHeight: 420, overflowY: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Machine</th>
              <th>Reason</th>
              <th className="num">Duration</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).length === 0 && (
              <tr>
                <td colSpan={4}>
                  <Empty>No downtime in the last 7 days</Empty>
                </td>
              </tr>
            )}
            {(data ?? []).map((event) => (
              <tr key={event.id}>
                <td className="code">{event.machine.code}</td>
                <td>
                  {event.reason.name}
                  <div className="muted small">{titleCase(event.reason.category)}</div>
                </td>
                <td className="num">
                  {event.ended_at ? (
                    duration(event.duration_minutes)
                  ) : (
                    <span className="badge bad">
                      <span className="dot" /> Open
                    </span>
                  )}
                </td>
                <td className="secondary small">{dateTime(event.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function MaintenanceList() {
  const { data, isLoading } = useMaintenance(true)
  const close = useCloseMaintenance()
  const { can } = useAuth()
  if (isLoading) return <Loading />

  return (
    <Card title="Open maintenance requests" flush>
      <div className="table-wrap" style={{ maxHeight: 420, overflowY: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Request</th>
              <th>Machine</th>
              <th>Priority</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(data ?? []).length === 0 && (
              <tr>
                <td colSpan={4}>
                  <Empty>Nothing outstanding</Empty>
                </td>
              </tr>
            )}
            {(data ?? []).map((request) => (
              <tr key={request.id}>
                <td>
                  <span className="code strong">{request.request_no}</span>
                  <div className="small">{request.title}</div>
                </td>
                <td className="code">{request.machine.code}</td>
                <td>
                  <span className={`badge ${request.priority === 'HIGH' ? 'bad' : 'neutral'}`}>
                    <span className="dot" /> {titleCase(request.priority)}
                  </span>
                </td>
                <td className="num">
                  {can('OPERATOR', 'PLANNER') && (
                    <button className="sm" onClick={() => close.mutate(request.id)}>
                      Close
                    </button>
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

function StopModal({ machine, onClose }: { machine: Machine; onClose: () => void }) {
  const { data: reasons } = useDowntimeReasons()
  const setStatus = useSetMachineStatus()
  const [reasonId, setReasonId] = useState<number | ''>('')
  const [status, setStatusValue] = useState<MachineStatus>('DOWN')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await setStatus.mutateAsync({
        id: machine.id,
        status,
        reason_id: Number(reasonId),
        note: note || undefined,
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title={`Stop ${machine.code}`}
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="stop-form" type="submit" disabled={!reasonId || setStatus.isPending}>
            {setStatus.isPending ? 'Recording...' : 'Record stop'}
          </button>
        </>
      }
    >
      <form id="stop-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Reason" note="planned reasons are excluded from availability">
          <select
            value={reasonId}
            onChange={(event) => setReasonId(Number(event.target.value))}
            required
            autoFocus
          >
            <option value="">Select a reason...</option>
            {(reasons ?? []).map((reason) => (
              <option key={reason.id} value={reason.id}>
                {reason.code} - {reason.name} ({titleCase(reason.category)})
              </option>
            ))}
          </select>
        </Field>
        <Field label="New state">
          <select value={status} onChange={(event) => setStatusValue(event.target.value as MachineStatus)}>
            {STATUSES.filter((value) => value === 'DOWN' || value === 'MAINTENANCE').map((value) => (
              <option key={value} value={value}>
                {titleCase(value)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Note" note="optional">
          <input value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
      </form>
    </Modal>
  )
}

function MaintenanceModal({ machine, onClose }: { machine: Machine; onClose: () => void }) {
  const create = useCreateMaintenance()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState('NORMAL')
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await create.mutateAsync({
        machine_id: machine.id,
        title,
        description: description || null,
        priority,
      })
      onClose()
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title={`Maintenance request · ${machine.code}`}
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="maintenance-form" type="submit" disabled={!title || create.isPending}>
            {create.isPending ? 'Raising...' : 'Raise request'}
          </button>
        </>
      }
    >
      <form id="maintenance-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Title">
          <input value={title} onChange={(event) => setTitle(event.target.value)} required autoFocus />
        </Field>
        <Field label="Description" note="optional">
          <textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        </Field>
        <Field label="Priority">
          <select value={priority} onChange={(event) => setPriority(event.target.value)}>
            <option value="LOW">Low</option>
            <option value="NORMAL">Normal</option>
            <option value="HIGH">High</option>
          </select>
        </Field>
      </form>
    </Modal>
  )
}
