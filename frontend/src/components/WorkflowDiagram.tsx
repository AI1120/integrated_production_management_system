/**
 * Workflow diagrams.
 *
 * Two shapes, both hand-laid inline SVG so they stay crisp, theme-reactive and
 * dependency-free:
 *
 *   <PipelineDiagram>     the end-to-end material flow across the plant
 *   <StateMachineDiagram> one entity's states and the transitions between them
 *
 * Fills and strokes come from CSS classes rather than JS-computed colours, so a
 * theme switch repaints them with no re-render.
 */
import type { FlowStage, WorkflowEntity } from '../api/types'
import { toneFor } from '../lib/status'

const NODE_W = 132
const NODE_H = 58
const GAP_X = 52
const ROW1_Y = 14
const ROW2_Y = 146

const slot = (i: number) => i * (NODE_W + GAP_X)

function NodeBox({
  x,
  y,
  label,
  count,
  unit,
  tone,
  terminal,
  title,
}: {
  x: number
  y: number
  label: string
  count: number
  unit?: string
  tone: string
  terminal?: boolean
  title?: string
}) {
  const empty = count === 0
  return (
    <g className={`wf-node ${tone}${empty ? ' empty' : ''}${terminal ? ' terminal' : ''}`}>
      {title && <title>{title}</title>}
      <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={9} />
      <text className="wf-label" x={x + NODE_W / 2} y={y + 21} textAnchor="middle">
        {label}
      </text>
      <text className="wf-count" x={x + NODE_W / 2} y={y + 44} textAnchor="middle">
        {count.toLocaleString()}
        {unit ? <tspan className="wf-unit"> {unit}</tspan> : null}
      </text>
    </g>
  )
}

/** Straight connector between two nodes on the same row. */
const Straight = ({ from, y, marker }: { from: number; y: number; marker: string }) => (
  <line
    className="wf-edge"
    x1={slot(from) + NODE_W}
    y1={y + NODE_H / 2}
    x2={slot(from + 1) - 6}
    y2={y + NODE_H / 2}
    markerEnd={`url(#${marker})`}
  />
)

/**
 * Curved connector from a row-1 node down to a row-2 branch node.
 *
 * `fanIndex` staggers the descent depth and the label height. Several branches
 * leaving the same state (an NCR disposition, say) would otherwise share one
 * inflection point and stack their labels on top of each other.
 */
function Branch({
  fromIndex,
  toX,
  label,
  marker,
  tone,
  fanIndex = 0,
}: {
  fromIndex: number
  toX: number
  label?: string
  marker: string
  tone: string
  fanIndex?: number
}) {
  const x1 = slot(fromIndex) + NODE_W / 2
  const y1 = ROW1_Y + NODE_H
  const x2 = toX + NODE_W / 2
  const y2 = ROW2_Y - 8
  // Later branches in a fan turn later and carry their label lower.
  const depth = 0.34 + 0.16 * Math.min(fanIndex, 3)
  const turnY = y1 + (y2 - y1) * depth
  const labelY = y1 + (y2 - y1) * depth - 4
  const straightDown = Math.abs(x2 - x1) < 1
  return (
    <g className={`wf-branch ${tone}`}>
      <path
        className="wf-edge dashed"
        d={`M ${x1} ${y1} C ${x1} ${turnY}, ${x2} ${turnY}, ${x2} ${y2}`}
        markerEnd={`url(#${marker})`}
        fill="none"
      />
      {label && (
        <text
          className="wf-edge-label"
          x={straightDown ? x1 : (x1 + x2) / 2}
          y={labelY}
          textAnchor="middle"
        >
          {label}
        </text>
      )}
    </g>
  )
}

/**
 * Connector from a row-2 state back up to the main path.
 *
 * Drawn under the row rather than over it, and entering its target from below,
 * so a recovery never gets mistaken for one of the forward arrows. Without
 * these the machine diagram reads as a one-way trip: broken down, never fixed.
 */
function Return({
  fromX,
  toIndex,
  label,
  marker,
  fanIndex = 0,
}: {
  fromX: number
  toIndex: number
  label?: string
  marker: string
  fanIndex?: number
}) {
  const x1 = fromX + NODE_W / 2
  const y1 = ROW2_Y
  const x2 = slot(toIndex) + NODE_W / 2
  const y2 = ROW1_Y + NODE_H + 6
  // Stagger so two recoveries into the same state do not trace one line.
  const depth = 0.5 + 0.14 * Math.min(fanIndex, 3)
  const turnY = y2 + (y1 - y2) * depth
  return (
    <g className="wf-branch return">
      <path
        className="wf-edge dashed return"
        d={`M ${x1} ${y1} C ${x1} ${turnY}, ${x2} ${turnY}, ${x2} ${y2}`}
        markerEnd={`url(#${marker})`}
        fill="none"
      />
      {label && (
        <text className="wf-edge-label" x={(x1 + x2) / 2} y={turnY + 4} textAnchor="middle">
          {label}
        </text>
      )}
    </g>
  )
}

/** A transition between two states that both sit on the second row. */
function SecondLevel({
  fromX,
  toX,
  label,
  marker,
}: {
  fromX: number
  toX: number
  label?: string
  marker: string
}) {
  const forward = toX > fromX
  const x1 = forward ? fromX + NODE_W : fromX
  const x2 = forward ? toX - 6 : toX + NODE_W + 6
  const y = ROW2_Y + NODE_H / 2
  return (
    <g className="wf-branch">
      <line className="wf-edge dashed" x1={x1} y1={y} x2={x2} y2={y} markerEnd={`url(#${marker})`} />
      {label && (
        <text className="wf-edge-label" x={(x1 + x2) / 2} y={y - 7} textAnchor="middle">
          {label}
        </text>
      )}
    </g>
  )
}

function Defs({ id }: { id: string }) {
  return (
    <defs>
      <marker id={`${id}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path className="wf-arrowhead" d="M 0 0 L 10 5 L 0 10 z" />
      </marker>
      <marker id={`${id}-arrow-muted`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path className="wf-arrowhead muted" d="M 0 0 L 10 5 L 0 10 z" />
      </marker>
    </defs>
  )
}

/* ------------------------------------------------------------------ */
/* End-to-end plant pipeline                                          */
/* ------------------------------------------------------------------ */
export function PipelineDiagram({
  flow,
  rejectBranch,
}: {
  flow: FlowStage[]
  rejectBranch: FlowStage[]
}) {
  const id = 'wf-pipe'
  // The reject path hangs off "Awaiting QC" - that is where a lot is blocked.
  const qcIndex = Math.max(flow.findIndex((s) => s.key === 'quarantine'), 0)
  const width = Math.max(slot(flow.length - 1) + NODE_W, slot(qcIndex + rejectBranch.length) + NODE_W)
  const height = ROW2_Y + NODE_H + 16

  const KIND_TONE: Record<string, string> = {
    store: 'good',
    gate: 'warn',
    process: 'info',
    reject: 'bad',
  }

  return (
    <div className="wf-scroll">
      <svg
        className="wf-svg"
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        style={{ minWidth: Math.min(width, 760) }}
        role="img"
        aria-label="End-to-end production flow with live counts at each stage"
      >
        <Defs id={id} />
        {flow.slice(0, -1).map((_, i) => (
          <Straight key={i} from={i} y={ROW1_Y} marker={`${id}-arrow`} />
        ))}
        {flow.map((stage, i) => (
          <NodeBox
            key={stage.key}
            x={slot(i)}
            y={ROW1_Y}
            label={stage.label}
            count={stage.count}
            unit={stage.unit}
            tone={KIND_TONE[stage.kind] ?? 'info'}
            title={stage.detail ?? undefined}
          />
        ))}

        {rejectBranch.map((stage, i) => {
          const x = slot(qcIndex + i)
          return (
            <g key={stage.key}>
              {i === 0 ? (
                <Branch
                  fromIndex={qcIndex}
                  toX={x}
                  label="fails inspection"
                  marker={`${id}-arrow-muted`}
                  tone="bad"
                />
              ) : (
                <line
                  className="wf-edge"
                  x1={slot(qcIndex + i - 1) + NODE_W}
                  y1={ROW2_Y + NODE_H / 2}
                  x2={x - 6}
                  y2={ROW2_Y + NODE_H / 2}
                  markerEnd={`url(#${id}-arrow-muted)`}
                />
              )}
              <NodeBox
                x={x}
                y={ROW2_Y}
                label={stage.label}
                count={stage.count}
                unit={stage.unit}
                tone="bad"
                title={stage.detail ?? undefined}
              />
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* One entity's state machine                                          */
/* ------------------------------------------------------------------ */
export function StateMachineDiagram({ entity }: { entity: WorkflowEntity }) {
  const id = `wf-${entity.key}`
  const byKey = new Map(entity.statuses.map((s) => [s.key, s]))
  const main = entity.main_path.filter((k) => byKey.has(k))
  const mainIndex = new Map(main.map((k, i) => [k, i]))

  // Branch targets sit on the second row, directly beneath the state they leave
  // from wherever that column is free - a vertical drop reads instantly, whereas
  // packing them left-to-right makes long branches cross the whole diagram.
  const branches = entity.branches.filter((b) => byKey.has(b.to) && mainIndex.has(b.from))
  const takenSlots = new Set<number>()
  const claim = (preferred: number) => {
    let column = Math.max(preferred, 0)
    while (takenSlots.has(column)) column += 1
    takenSlots.add(column)
    return column
  }
  const branchX = branches.map((b) => slot(claim(mainIndex.get(b.from) ?? 0)))

  // Any status not on the main path and not a branch target still has to appear.
  const placed = new Set([...main, ...branches.map((b) => b.to)])
  const orphans = entity.statuses.filter((s) => !placed.has(s.key))
  const orphanX = orphans.map(() => slot(claim(0)))

  // Where every second-row node ended up, so edges between them can be drawn.
  const row2X = new Map<string, number>([
    ...branches.map((b, i) => [b.to, branchX[i]] as const),
    ...orphans.map((node, i) => [node.key, orphanX[i]] as const),
  ])

  // A transition whose source is itself a branch target used to be dropped in
  // silence, leaving its destination floating with no edge into it at all.
  const secondLevel = entity.branches.filter(
    (b) => byKey.has(b.to) && !mainIndex.has(b.from) && row2X.has(b.from) && row2X.has(b.to),
  )

  const returns = (entity.returns ?? []).filter(
    (r) => row2X.has(r.from) && mainIndex.has(r.to),
  )

  const width = Math.max(
    slot(Math.max(main.length - 1, 0)) + NODE_W,
    ...branchX.map((x) => x + NODE_W),
    ...orphanX.map((x) => x + NODE_W),
    NODE_W,
  )
  const hasRow2 = branches.length > 0 || orphans.length > 0
  const height = (hasRow2 ? ROW2_Y + NODE_H : ROW1_Y + NODE_H) + 16

  return (
    <div className="wf-scroll">
      <svg
        className="wf-svg"
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        style={{ minWidth: Math.min(width, 620) }}
        role="img"
        aria-label={`${entity.label} states and transitions, with the number of records currently in each`}
      >
        <Defs id={id} />
        {main.slice(0, -1).map((_, i) => (
          <Straight key={i} from={i} y={ROW1_Y} marker={`${id}-arrow`} />
        ))}
        {main.map((key, i) => {
          const node = byKey.get(key)!
          return (
            <NodeBox
              key={key}
              x={slot(i)}
              y={ROW1_Y}
              label={node.label}
              count={node.count}
              tone={toneFor(entity.key, key)}
              terminal={node.terminal}
            />
          )
        })}

        {branches.map((b, i) => {
          const node = byKey.get(b.to)!
          return (
            <g key={b.to}>
              <Branch
                fromIndex={mainIndex.get(b.from) ?? 0}
                toX={branchX[i]}
                label={b.label}
                marker={`${id}-arrow-muted`}
                tone={toneFor(entity.key, b.to)}
                fanIndex={branches.filter((o, j) => j < i && o.from === b.from).length}
              />
              <NodeBox
                x={branchX[i]}
                y={ROW2_Y}
                label={node.label}
                count={node.count}
                tone={toneFor(entity.key, b.to)}
                terminal={node.terminal}
              />
            </g>
          )
        })}

        {orphans.map((node, i) => (
          <NodeBox
            key={node.key}
            x={orphanX[i]}
            y={ROW2_Y}
            label={node.label}
            count={node.count}
            tone={toneFor(entity.key, node.key)}
            terminal={node.terminal}
          />
        ))}

        {secondLevel.map((b) => (
          <SecondLevel
            key={`${b.from}-${b.to}`}
            fromX={row2X.get(b.from)!}
            toX={row2X.get(b.to)!}
            label={b.label}
            marker={`${id}-arrow-muted`}
          />
        ))}

        {returns.map((r, i) => (
          <Return
            key={`${r.from}-${r.to}`}
            fromX={row2X.get(r.from)!}
            toIndex={mainIndex.get(r.to)!}
            label={r.label}
            marker={`${id}-arrow-muted`}
            fanIndex={returns.filter((o, j) => j < i && o.to === r.to).length}
          />
        ))}
      </svg>
    </div>
  )
}
