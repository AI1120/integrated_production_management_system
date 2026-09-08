import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useDashboard } from '../api/hooks'
import { DowntimeBars, ProductionTrend } from '../components/charts'
import { Layout } from '../components/Layout'
import { Alert, Card, Empty, Loading, Meter, RankList } from '../components/ui'
import { dateTime, num, pct, qty, titleCase } from '../lib/format'

const OEE_TARGET = 0.85

function oeeTone(value: number): 'good' | 'warn' | 'bad' {
  if (value >= OEE_TARGET) return 'good'
  if (value >= 0.6) return 'warn'
  return 'bad'
}

export function Dashboard() {
  const [days, setDays] = useState(7)
  const { data, isLoading, error } = useDashboard(days)

  return (
    <Layout
      title="Plant dashboard"
      subtitle={data ? `Updated ${dateTime(data.generated_at)}` : 'Loading plant status'}
      actions={
        <select value={days} onChange={(event) => setDays(Number(event.target.value))} style={{ width: 140 }}>
          <option value={1}>Today</option>
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
        </select>
      }
    >
      {error && <Alert tone="error">Could not load the dashboard. Is the API running?</Alert>}
      {isLoading && <Loading />}

      {data && (
        <div className="stack">
          <div className="kpis">
            {data.kpis.map((kpi) => {
              const alert =
                (kpi.key === 'late_orders' || kpi.key === 'open_ncrs') && kpi.value > 0
              return (
                <div className={`kpi${alert ? ' alert' : ''}`} key={kpi.key}>
                  <div className="label">{kpi.label}</div>
                  <div className="value">
                    {num(kpi.value, 1)}
                    {kpi.unit && <span className="unit">{kpi.unit}</span>}
                  </div>
                  {kpi.hint && <div className="hint">{kpi.hint}</div>}
                </div>
              )
            })}
          </div>

          <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.55fr) minmax(0, 1fr)' }}>
            <Card title="Daily output" hint="Units booked at the final routing step">
              <ProductionTrend data={data.production_trend} />
            </Card>

            <Card title="OEE by machine" hint={`Target ${pct(OEE_TARGET, 0)} · window average ${pct(data.plant_oee.oee)}`} flush>
              {data.plant_oee.machines.length === 0 ? (
                <Empty>No machines configured</Empty>
              ) : (
                <div className="rank-list">
                  {[...data.plant_oee.machines]
                    .sort((a, b) => b.oee - a.oee)
                    .map((machine) => (
                      <div className="rank-row" key={machine.machine_id}>
                        <div className="rank-label">{machine.machine_code}</div>
                        <div className="rank-value">{pct(machine.oee)}</div>
                        <div className="rank-sub">
                          A {pct(machine.availability, 0)} · P {pct(machine.performance, 0)} · Q{' '}
                          {pct(machine.quality, 0)}
                        </div>
                        <div style={{ gridColumn: '1 / -1', marginTop: 2 }}>
                          <Meter value={machine.oee} tone={oeeTone(machine.oee)} />
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </Card>
          </div>

          <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}>
            <Card title="Downtime losses" hint="Unplanned stops only - planned time is not a machine loss">
              <DowntimeBars
                data={data.downtime_pareto.map((row) => ({
                  name: row.name,
                  minutes: row.minutes,
                  planned: row.category === 'PLANNED',
                }))}
              />
            </Card>

            <Card title="Below safety stock" hint="Order these before the line stops" flush>
              <RankList
                emptyText="Every part is above its safety level"
                rows={data.low_stock.map((row) => ({
                  key: row.code,
                  label: (
                    <>
                      <span className="code">{row.code}</span>{' '}
                      <span className="secondary">{row.name}</span>
                    </>
                  ),
                  sub: `${qty(row.on_hand)} on hand of ${qty(row.safety_stock)} ${row.uom}`,
                  value: row.shortfall,
                  display: `-${qty(row.shortfall)}`,
                }))}
              />
            </Card>
          </div>

          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
            <Card title="Work orders" flush>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {data.order_status.length === 0 && (
                      <tr>
                        <td colSpan={2}>
                          <Empty>No orders yet</Empty>
                        </td>
                      </tr>
                    )}
                    {data.order_status.map((slice) => (
                      <tr key={slice.label}>
                        <td>{titleCase(slice.label)}</td>
                        <td className="num strong">{num(slice.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Machine state" flush>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {data.machine_status.map((slice) => (
                      <tr key={slice.label}>
                        <td>{titleCase(slice.label)}</td>
                        <td className="num strong">{num(slice.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card
              title="Top defects"
              hint="By quantity in the window"
              flush
              actions={
                <Link className="btn sm" to="/quality">
                  Open quality
                </Link>
              }
            >
              <div className="table-wrap">
                <table>
                  <tbody>
                    {data.top_defects.length === 0 && (
                      <tr>
                        <td>
                          <Empty>No defects logged</Empty>
                        </td>
                      </tr>
                    )}
                    {data.top_defects.map((defect) => (
                      <tr key={defect.code}>
                        <td>
                          <span className="code">{defect.code}</span>{' '}
                          <span className="secondary">{defect.name}</span>
                        </td>
                        <td className="num strong">{qty(defect.qty)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </div>
      )}
    </Layout>
  )
}
