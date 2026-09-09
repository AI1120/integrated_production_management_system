import { Link } from 'react-router-dom'

import { useWorkflow } from '../api/hooks'
import { Layout } from '../components/Layout'
import { PipelineDiagram, StateMachineDiagram } from '../components/WorkflowDiagram'
import { Alert, Card, Loading } from '../components/ui'
import { dateTime } from '../lib/format'

const LEGEND = [
  { tone: 'good', label: 'Healthy / released' },
  { tone: 'warn', label: 'Holding / in progress' },
  { tone: 'bad', label: 'Blocked / rejected' },
  { tone: 'info', label: 'Queued' },
  { tone: 'vacant', label: 'Nothing in this state' },
]

function Legend() {
  return (
    <div className="wf-legend">
      {LEGEND.map((entry) => (
        <span className="key" key={entry.label}>
          <span className={`chip ${entry.tone}`} />
          {entry.label}
        </span>
      ))}
      <span className="key muted">
        Dashed arrow = exception path · green arrow = back to the happy path · thick border =
        terminal state
      </span>
    </div>
  )
}

export function Workflow() {
  const { data, isLoading, error } = useWorkflow()

  return (
    <Layout
      title="Process & status map"
      subtitle={
        data
          ? `Every state in the system, with what is sitting in it right now · updated ${dateTime(data.generated_at)}`
          : 'Loading the workflow'
      }
    >
      {error && <Alert tone="error">Could not load the workflow map. Is the API running?</Alert>}
      {isLoading && <Loading />}

      {data && (
        <div className="stack">
          <Card
            title="End-to-end production flow"
            hint="Material enters at the raw store and leaves as finished goods. Counts are live."
            flush
          >
            <Legend />
            <div style={{ padding: '4px 16px 12px' }}>
              <PipelineDiagram flow={data.flow} rejectBranch={data.reject_branch} />
            </div>
          </Card>

          <div className="stack">
            {data.entities.map((entity) => (
              <Card key={entity.key} title={entity.label} hint={entity.hint ?? undefined} flush>
                <div style={{ padding: '12px 16px 8px' }}>
                  <StateMachineDiagram entity={entity} />
                </div>
                <details>
                  <summary className="wf-summary">All {entity.statuses.length} statuses in a table</summary>
                <div className="table-wrap" style={{ borderTop: '1px solid var(--border)' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th className="num">Records</th>
                        <th>Kind</th>
                      </tr>
                    </thead>
                    <tbody>
                      {entity.statuses.map((status) => (
                        <tr key={status.key}>
                          <td className="strong">{status.label}</td>
                          <td className="num">{status.count.toLocaleString()}</td>
                          <td className="muted small">
                            {status.terminal
                              ? 'Terminal'
                              : entity.main_path.includes(status.key)
                                ? 'Main path'
                                : 'Exception'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                </details>
              </Card>
            ))}
          </div>

          <Card title="Where to act" hint="The diagram above is read-only; these are the screens that move work along">
            <div className="row">
              <Link className="btn" to="/orders">
                Work orders
              </Link>
              <Link className="btn" to="/terminal">
                Shop floor terminal
              </Link>
              <Link className="btn" to="/inventory">
                Inventory & lot trace
              </Link>
              <Link className="btn" to="/quality">
                Inspections & NCRs
              </Link>
              <Link className="btn" to="/equipment">
                Machines & OEE
              </Link>
            </div>
          </Card>
        </div>
      )}
    </Layout>
  )
}
