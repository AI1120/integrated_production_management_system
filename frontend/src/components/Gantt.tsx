/**
 * Machine-loading Gantt.
 *
 * The x-axis is *working* time, not wall-clock time. On a single-shift plant a
 * wall-clock axis is two-thirds empty night, which squeezes every bar into an
 * unreadable sliver; the backend supplies each operation's offset in productive
 * minutes so the idle hours take up no width. Day boundaries are marked, so the
 * compression stays visible rather than hidden.
 */
import type { Schedule } from '../api/types'

const ROW_H = 30
const BAR_H = 19
const LABEL_W = 78
const PAD_R = 12
const TOP = 26

/** Colour by product, not by order - there are three items and many orders. */
const ITEM_CLASS = ['g-a', 'g-b', 'g-c', 'g-d']

export function Gantt({ schedule, height }: { schedule: Schedule; height?: number }) {
  const machines = Array.from(new Set(schedule.operations.map((o) => o.machine_code))).sort()
  if (!machines.length) {
    return <div className="empty">Nothing to schedule — the order book is empty.</div>
  }

  const items = Array.from(new Set(schedule.operations.map((o) => o.item_code))).sort()
  const itemClass = new Map(items.map((code, i) => [code, ITEM_CLASS[i % ITEM_CLASS.length]]))

  const totalMinutes = Math.max(
    ...schedule.operations.map((o) => o.offset_minutes + o.work_minutes),
    1,
  )
  const plotW = 1000
  const width = LABEL_W + plotW + PAD_R
  const plotH = machines.length * ROW_H
  const svgH = TOP + plotH + 26

  const x = (minutes: number) => LABEL_W + (minutes / totalMinutes) * plotW
  const rowY = (machine: string) => TOP + machines.indexOf(machine) * ROW_H

  return (
    <div className="gantt-wrap">
      <div className="gantt-legend">
        {items.map((code) => (
          <span className="key" key={code}>
            <span className={`swatch ${itemClass.get(code)}`} />
            {code}
          </span>
        ))}
        <span className="muted small">
          Axis is production time — nights and weekends are removed
        </span>
      </div>

      <div className="wf-scroll">
        <svg
          className="gantt"
          viewBox={`0 0 ${width} ${svgH}`}
          width={width}
          height={height ?? svgH}
          style={{ minWidth: 760 }}
          role="img"
          aria-label={`Machine loading schedule under the ${schedule.rule} rule, ${schedule.operations.length} operations across ${machines.length} machines`}
        >
          {/* Day boundaries. The gridline is always drawn; the label is dropped
              when it would collide with the previous one or run off the right
              edge, because two overlapping dates read as neither. */}
          {(() => {
            let lastLabelX = -Infinity
            return schedule.day_marks.map((mark) => {
              const mx = x(mark.offset_minutes)
              const showLabel = mx - lastLabelX >= 64 && mx < LABEL_W + plotW - 52
              if (showLabel) lastLabelX = mx
              return (
                <g key={mark.label}>
                  <line className="gantt-day" x1={mx} y1={TOP - 6} x2={mx} y2={TOP + plotH} />
                  {showLabel && (
                    <text className="gantt-daylabel" x={mx + 4} y={TOP - 11}>
                      {mark.label}
                    </text>
                  )}
                </g>
              )
            })
          })()}

          {/* machine rows */}
          {machines.map((machine) => (
            <g key={machine}>
              <line
                className="gantt-rule"
                x1={LABEL_W}
                y1={rowY(machine) + ROW_H}
                x2={LABEL_W + plotW}
                y2={rowY(machine) + ROW_H}
              />
              <text className="gantt-machine" x={0} y={rowY(machine) + ROW_H / 2 + 4}>
                {machine}
              </text>
            </g>
          ))}

          {/* operations */}
          {schedule.operations.map((op) => {
            const bx = x(op.offset_minutes)
            const bw = Math.max((op.work_minutes / totalMinutes) * plotW, 2)
            const by = rowY(op.machine_code) + (ROW_H - BAR_H) / 2
            const setupW = Math.min((op.setup_minutes / totalMinutes) * plotW, bw)
            return (
              <g className={`gantt-bar ${itemClass.get(op.item_code)}`} key={op.operation_id}>
                <title>
                  {`${op.order_no} · ${op.item_code} · op ${op.seq} ${op.name}\n`}
                  {`${op.machine_code} · ${op.qty} units\n`}
                  {`setup ${op.setup_minutes.toFixed(0)} min + run ${op.run_minutes.toFixed(0)} min\n`}
                  {`${new Date(op.start).toLocaleString()} → ${new Date(op.end).toLocaleString()}`}
                </title>
                <rect x={bx} y={by} width={bw} height={BAR_H} rx={2.5} />
                {/* setup shown as a hatched head - it is capacity spent making nothing */}
                {setupW > 1.5 && (
                  <rect className="gantt-setup" x={bx} y={by} width={setupW} height={BAR_H} rx={2.5} />
                )}
                {bw > 46 && (
                  <text className="gantt-oplabel" x={bx + bw / 2} y={by + BAR_H / 2 + 3.5}>
                    {op.order_no.replace('WO-', '')}
                  </text>
                )}
              </g>
            )
          })}

          {/* axis */}
          <line className="gantt-axis" x1={LABEL_W} y1={TOP + plotH} x2={LABEL_W + plotW} y2={TOP + plotH} />
          <text className="gantt-tick" x={LABEL_W} y={TOP + plotH + 15}>
            0 h
          </text>
          <text className="gantt-tick" x={LABEL_W + plotW} y={TOP + plotH + 15} textAnchor="end">
            {(totalMinutes / 60).toFixed(0)} h of production time
          </text>
        </svg>
      </div>
    </div>
  )
}
