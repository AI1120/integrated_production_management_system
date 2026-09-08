import { useState } from 'react'

import { errorMessage } from '../api/client'
import { useApplySchedule, useOptimization } from '../api/hooks'
import { Gantt } from '../components/Gantt'
import { Layout } from '../components/Layout'
import { Alert, Card, Empty, Loading, Meter, Modal } from '../components/ui'
import { useAuth } from '../lib/auth'
import { dateTime, money, num, pct, qty } from '../lib/format'

const OBJECTIVES = [
  { key: 'total_lateness_hours', label: 'Least total lateness' },
  { key: 'late_orders', label: 'Fewest late orders' },
  { key: 'makespan_hours', label: 'Clear the book soonest' },
  { key: 'max_lateness_hours', label: 'Best worst-case order' },
]

const RULES = ['PRIORITY', 'EDD', 'SPT', 'LPT', 'CR']

export function Optimize() {
  const { can } = useAuth()
  const [rule, setRule] = useState('PRIORITY')
  const [objective, setObjective] = useState('total_lateness_hours')
  const [horizon, setHorizon] = useState(30)
  const [confirming, setConfirming] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError } = useOptimization({
    rule,
    horizon_days: horizon,
    objective,
  })
  const apply = useApplySchedule()

  async function applySchedule() {
    setError(null)
    try {
      await apply.mutateAsync({ rule, horizon_days: horizon })
      setConfirming(false)
      setNotice(`Planned dates rewritten from the ${rule} schedule.`)
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Layout
      title="Optimisation"
      subtitle={
        data
          ? `Process, time and cost across ${data.schedule.orders.length} open orders · ${dateTime(data.generated_at)}`
          : 'Analysing the order book'
      }
      actions={
        <>
          <select value={rule} onChange={(e) => setRule(e.target.value)} style={{ width: 118 }}>
            {RULES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <select value={objective} onChange={(e) => setObjective(e.target.value)} style={{ width: 190 }}>
            {OBJECTIVES.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
          <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} style={{ width: 120 }}>
            {[7, 14, 30, 60].map((d) => (
              <option key={d} value={d}>
                {d}-day horizon
              </option>
            ))}
          </select>
        </>
      }
    >
      {isError && <Alert tone="error">Could not build a schedule. Is the API running?</Alert>}
      {isLoading && <Loading />}

      {data && (
        <div className="stack">
          {notice && <Alert tone="ok">{notice}</Alert>}
          {error && <Alert tone="error">{error}</Alert>}

          {/* ---- headline numbers ---- */}
          <div className="kpis">
            <div className="kpi">
              <div className="label">Makespan</div>
              <div className="value">
                {num(data.schedule.makespan_hours, 1)}
                <span className="unit">h</span>
              </div>
              <div className="hint">Production time to clear the book</div>
            </div>
            <div className={`kpi${data.schedule.late_orders ? ' alert' : ''}`}>
              <div className="label">Late orders</div>
              <div className="value">{data.schedule.late_orders}</div>
              <div className="hint">of {data.schedule.orders.length} scheduled</div>
            </div>
            <div className="kpi">
              <div className="label">Total lateness</div>
              <div className="value">
                {num(data.schedule.total_lateness_hours, 1)}
                <span className="unit">h</span>
              </div>
              <div className="hint">Worst single order {num(data.schedule.max_lateness_hours, 1)} h</div>
            </div>
            <div className="kpi">
              <div className="label">Flow efficiency</div>
              <div className="value">
                {num(data.flow.efficiency * 100, 0)}
                <span className="unit">%</span>
              </div>
              <div className="hint">
                {num(data.flow.work_hours, 0)} h work of {num(data.flow.flow_hours, 0)} h elapsed
              </div>
            </div>
            <div className={`kpi${data.cost.total_variance > 0 ? ' alert' : ''}`}>
              <div className="label">Cost variance</div>
              <div className="value">
                {data.cost.total_variance > 0 ? '+' : ''}
                {num(data.cost.variance_pct, 1)}
                <span className="unit">%</span>
              </div>
              <div className="hint">{money(data.cost.total_variance)} vs standard</div>
            </div>
            <div className="kpi">
              <div className="label">Scrap cost</div>
              <div className="value">{money(data.cost.scrap_cost)}</div>
              <div className="hint">Value destroyed in the window</div>
            </div>
          </div>

          {/* ---- recommendations ---- */}
          <Card
            title="What to do"
            hint="Ranked by size of the prize. Every figure comes from the schedule or the cost roll-up."
            flush
          >
            {data.recommendations.length === 0 ? (
              <Empty>Nothing to improve — no constraint, no lateness, no variance.</Empty>
            ) : (
              data.recommendations.map((rec, index) => (
                <div className={`rec ${rec.severity}`} key={`${rec.area}-${index}`}>
                  <span className={`rec-area ${rec.area}`}>{rec.area}</span>
                  <div className="rec-title">{rec.title}</div>
                  <div className="rec-value">{rec.value}</div>
                  <div className="rec-detail">{rec.detail}</div>
                  <div className="rec-action">{rec.action}</div>
                </div>
              ))
            )}
          </Card>

          {/* ---- schedule ---- */}
          <Card
            title={`Machine loading · ${rule}`}
            hint="Finite capacity: routing sequence, one job per machine, shift calendar. Hover a bar for detail."
            actions={
              can('PLANNER') ? (
                <button className="primary sm" onClick={() => setConfirming(true)}>
                  Apply to order book
                </button>
              ) : undefined
            }
          >
            <Gantt schedule={data.schedule} />
            {data.schedule.unscheduled.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <Alert tone="error">
                  {data.schedule.unscheduled.length} order(s) could not be placed:{' '}
                  {data.schedule.unscheduled.map((u) => `${u.order_no} (${u.reason})`).join('; ')}
                </Alert>
              </div>
            )}
          </Card>

          <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 1fr)' }}>
            {/* ---- rule comparison ---- */}
            <Card
              title="Sequencing options"
              hint={`Same orders, same machines — judged on ${data.comparison.objective_label.toLowerCase()}`}
              flush
            >
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Rule</th>
                      <th className="num">Makespan</th>
                      <th className="num">Lateness</th>
                      <th className="num">Late</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.comparison.results.map((result) => (
                      <tr
                        key={result.rule}
                        className={`rule-row${result.rule === data.comparison.best_rule ? ' best' : ''}`}
                      >
                        <td>
                          <span className="code strong">{result.rule}</span>
                          <div className="muted small">{result.description}</div>
                        </td>
                        <td className="num">{num(result.makespan_hours, 1)} h</td>
                        <td className="num">{num(result.total_lateness_hours, 1)} h</td>
                        <td className="num">{result.late_orders}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.comparison.improvement > 0 && (
                <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)' }}>
                  <strong>{data.comparison.best_rule}</strong> beats{' '}
                  {data.comparison.baseline_rule} by {num(data.comparison.improvement, 1)} h (
                  {num(data.comparison.improvement_pct, 0)}%).
                </div>
              )}
            </Card>

            {/* ---- capacity ---- */}
            <Card
              title="Capacity"
              hint={
                data.bottleneck?.is_constraint
                  ? `${data.bottleneck.work_center_code} is the constraint`
                  : 'No work centre is capacity-constrained'
              }
              flush
            >
              <div className="rank-list">
                {data.schedule.utilisation.map((row) => (
                  <div className="rank-row" key={row.work_center_id}>
                    <div className="rank-label">
                      <span className="code">{row.work_center_code}</span>{' '}
                      <span className="muted small">{row.machines} mc</span>
                    </div>
                    <div className="rank-value">{pct(row.utilisation, 0)}</div>
                    <div className="rank-sub">
                      {num(row.loaded_hours, 1)} h of {num(row.capacity_hours, 1)} h
                      {row.setup_hours > 0 && ` · ${num(row.setup_hours, 1)} h setup`}
                    </div>
                    <div style={{ gridColumn: '1 / -1', marginTop: 2 }}>
                      <Meter
                        value={row.utilisation}
                        tone={row.utilisation >= 0.85 ? 'bad' : row.utilisation >= 0.6 ? 'warn' : 'good'}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* ---- cost ---- */}
          <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.25fr) minmax(0, 1fr)' }}>
            <Card title="Cost variance by order" hint="Actual against standard, worst first" flush>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Order</th>
                      <th className="num">Standard</th>
                      <th className="num">Actual</th>
                      <th className="num">Variance</th>
                      <th className="num">Unit cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.cost.worst_orders.length === 0 && (
                      <tr>
                        <td colSpan={5}>
                          <Empty>No completed orders to cost</Empty>
                        </td>
                      </tr>
                    )}
                    {data.cost.worst_orders.map((order) => (
                      <tr key={order.order_id}>
                        <td>
                          <span className="code strong">{order.order_no}</span>
                          <div className="muted small">
                            {order.item_code} · {qty(order.qty_produced)} made
                          </div>
                        </td>
                        <td className="num">{money(order.standard_total)}</td>
                        <td className="num">{money(order.actual_total)}</td>
                        <td
                          className="num strong"
                          style={{ color: order.total_variance > 0 ? 'var(--critical)' : 'var(--good)' }}
                        >
                          {order.total_variance > 0 ? '+' : ''}
                          {money(order.total_variance)}
                        </td>
                        <td className="num secondary">{money(order.unit_cost_actual)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card
              title="Scrap ranked by money"
              hint="A frequent cheap defect and a rare expensive one look identical on a count"
              flush
            >
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Defect</th>
                      <th className="num">Units</th>
                      <th className="num">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.scrap_cost.length === 0 && (
                      <tr>
                        <td colSpan={3}>
                          <Empty>No scrap recorded in the window</Empty>
                        </td>
                      </tr>
                    )}
                    {data.scrap_cost.map((row) => (
                      <tr key={row.code}>
                        <td>
                          <span className="code">{row.code}</span>
                          <div className="muted small">{row.name}</div>
                        </td>
                        <td className="num">{qty(row.qty)}</td>
                        <td className="num strong">{money(row.cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          {/* ---- setup savings ---- */}
          {data.setups.length > 0 && (
            <Card
              title="Setup that can be avoided"
              hint="Orders for the same part at the same work centre each pay their own changeover"
              flush
            >
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Part</th>
                      <th>Work centre</th>
                      <th className="num">Orders</th>
                      <th className="num">Setup each</th>
                      <th className="num">Avoidable</th>
                      <th className="num">Value</th>
                      <th>Batch these</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.setups.map((row) => (
                      <tr key={`${row.item_code}-${row.work_center_code}`}>
                        <td className="code strong">{row.item_code}</td>
                        <td className="code">{row.work_center_code}</td>
                        <td className="num">{row.orders}</td>
                        <td className="num secondary">{num(row.setup_minutes_each, 0)} min</td>
                        <td className="num strong">{num(row.saveable_minutes, 0)} min</td>
                        <td className="num">{money(row.saveable_cost)}</td>
                        <td className="muted small">{row.order_nos.slice(0, 3).join(', ')}
                          {row.order_nos.length > 3 && ` +${row.order_nos.length - 3}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}

      {confirming && data && (
        <Modal
          title="Apply schedule to the order book"
          onClose={() => setConfirming(false)}
          footer={
            <>
              <button onClick={() => setConfirming(false)}>Cancel</button>
              <button className="primary" onClick={applySchedule} disabled={apply.isPending}>
                {apply.isPending ? 'Applying...' : `Rewrite ${data.schedule.orders.length} orders`}
              </button>
            </>
          }
        >
          <div className="stack" style={{ gap: 12 }}>
            <p>
              This writes the <strong>{rule}</strong> schedule onto the order book as planned start and
              end dates for {data.schedule.orders.length} orders. It does not release, start or change
              any quantity.
            </p>
            <Alert tone="info">
              Existing planned dates will be overwritten. The schedule assumes nothing else is added
              before it runs.
            </Alert>
          </div>
        </Modal>
      )}
    </Layout>
  )
}
