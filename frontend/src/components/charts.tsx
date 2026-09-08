/**
 * Chart layer.
 *
 * Series colours live in index.css as --series-1..4 and were validated for CVD
 * separation and surface contrast in both themes (see the palette note there).
 * They are read back through getComputedStyle so a theme change repaints the
 * charts without duplicating the hex values in JS.
 */
import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export interface Tokens {
  series: string[]
  grid: string
  axis: string
  muted: string
  surface: string
  text: string
}

const FALLBACK: Tokens = {
  series: ['#2a78d6', '#eb6834', '#1baf7a', '#e34948'],
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  muted: '#898781',
  surface: '#fcfcfb',
  text: '#0b0b0b',
}

function readTokens(): Tokens {
  if (typeof window === 'undefined') return FALLBACK
  const style = getComputedStyle(document.documentElement)
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback
  return {
    series: [
      read('--series-1', FALLBACK.series[0]),
      read('--series-2', FALLBACK.series[1]),
      read('--series-3', FALLBACK.series[2]),
      read('--series-4', FALLBACK.series[3]),
    ],
    grid: read('--grid', FALLBACK.grid),
    axis: read('--axis', FALLBACK.axis),
    muted: read('--text-muted', FALLBACK.muted),
    surface: read('--surface', FALLBACK.surface),
    text: read('--text-primary', FALLBACK.text),
  }
}

/** Re-reads the palette when the OS scheme or the app theme attribute changes. */
export function useTokens(): Tokens {
  const [tokens, setTokens] = useState<Tokens>(readTokens)

  useEffect(() => {
    const refresh = () => setTokens(readTokens())
    refresh()
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', refresh)
    const observer = new MutationObserver(refresh)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      media.removeEventListener('change', refresh)
      observer.disconnect()
    }
  }, [])

  return tokens
}

interface TooltipRow {
  name: string
  value: number
  color: string
}

function VizTooltip({
  active,
  label,
  payload,
  unit,
  format,
}: {
  active?: boolean
  label?: string | number
  payload?: { name?: string; value?: number; color?: string; fill?: string }[]
  unit?: string
  format?: (value: number) => string
}) {
  if (!active || !payload?.length) return null
  const rows: TooltipRow[] = payload
    .filter((entry) => entry.value != null)
    .map((entry) => ({
      name: entry.name ?? '',
      value: entry.value as number,
      color: entry.color ?? entry.fill ?? 'currentColor',
    }))
  return (
    <div className="viz-tooltip">
      <div className="t-label">{label}</div>
      {rows.map((row) => (
        <div className="t-row" key={row.name}>
          <span className="k">
            <span className="swatch" style={{ background: row.color, width: 9, height: 9, borderRadius: 3 }} />
            {row.name}
          </span>
          <span className="v">
            {format ? format(row.value) : row.value.toLocaleString()}
            {unit ?? ''}
          </span>
        </div>
      ))}
    </div>
  )
}

export function ChartLegend({ keys }: { keys: { label: string; color: string }[] }) {
  return (
    <div className="chart-legend">
      {keys.map((key) => (
        <span className="key" key={key.label}>
          <span className="swatch" style={{ background: key.color }} />
          {key.label}
        </span>
      ))}
    </div>
  )
}

/**
 * Daily good vs scrap output. Stacked so the bar height reads as total units
 * off the line, with the split visible inside it. A 2px surface stroke keeps the
 * two fills from touching.
 */
export function ProductionTrend({
  data,
  height = 240,
}: {
  data: { label: string; good: number; scrap: number }[]
  height?: number
}) {
  const tokens = useTokens()
  const [good, , , scrap] = tokens.series

  if (!data.some((point) => point.good || point.scrap)) {
    return <div className="empty">No production reported in this window</div>
  }

  return (
    <>
      <ChartLegend
        keys={[
          { label: 'Good', color: good },
          { label: 'Scrap', color: scrap },
        ]}
      />
      <div style={{ width: '100%', height, marginTop: 10 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -14 }} barCategoryGap="26%">
            <CartesianGrid stroke={tokens.grid} strokeDasharray="0" vertical={false} />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={{ stroke: tokens.axis }}
              tick={{ fill: tokens.muted, fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={52}
              tick={{ fill: tokens.muted, fontSize: 11 }}
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: tokens.grid, fillOpacity: 0.45 }}
              content={<VizTooltip unit=" pcs" />}
            />
            <Bar
              dataKey="good"
              name="Good"
              stackId="output"
              fill={good}
              stroke={tokens.surface}
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Bar
              dataKey="scrap"
              name="Scrap"
              stackId="output"
              fill={scrap}
              stroke={tokens.surface}
              strokeWidth={2}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}

/**
 * OEE broken into its three factors per machine. Grouped rather than stacked -
 * OEE is the product of the three, so stacking them would imply a sum that does
 * not exist. Always paired with the OEE table, which carries the exact numbers.
 */
export function OeeFactors({
  data,
  height = 260,
}: {
  data: { machine: string; availability: number; performance: number; quality: number }[]
  height?: number
}) {
  const tokens = useTokens()
  const [availability, performance, quality] = tokens.series

  if (!data.length) return <div className="empty">No machines configured</div>

  return (
    <>
      <ChartLegend
        keys={[
          { label: 'Availability', color: availability },
          { label: 'Performance', color: performance },
          { label: 'Quality', color: quality },
        ]}
      />
      <div style={{ width: '100%', height, marginTop: 10 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -14 }} barGap={2} barCategoryGap="22%">
            <CartesianGrid stroke={tokens.grid} vertical={false} />
            <XAxis
              dataKey="machine"
              tickLine={false}
              axisLine={{ stroke: tokens.axis }}
              tick={{ fill: tokens.muted, fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={52}
              domain={[0, 1]}
              tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              tick={{ fill: tokens.muted, fontSize: 11 }}
            />
            <Tooltip
              cursor={{ fill: tokens.grid, fillOpacity: 0.45 }}
              content={<VizTooltip format={(value) => `${(value * 100).toFixed(1)}%`} />}
            />
            <Legend content={() => null} />
            <Bar dataKey="availability" name="Availability" fill={availability} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="performance" name="Performance" fill={performance} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="quality" name="Quality" fill={quality} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}

/** Downtime minutes by reason, biggest loss first. One series, so no legend. */
export function DowntimeBars({
  data,
  height = 230,
}: {
  data: { name: string; minutes: number; planned: boolean }[]
  height?: number
}) {
  const tokens = useTokens()
  if (!data.length) return <div className="empty">No downtime recorded in this window</div>

  return (
    <div style={{ width: '100%', height, marginTop: 4 }}>
      <ResponsiveContainer>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
          barCategoryGap="24%"
        >
          <CartesianGrid stroke={tokens.grid} horizontal={false} />
          <XAxis
            type="number"
            tickLine={false}
            axisLine={{ stroke: tokens.axis }}
            tick={{ fill: tokens.muted, fontSize: 11 }}
            tickFormatter={(value: number) => `${value}m`}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={132}
            tickLine={false}
            axisLine={false}
            tick={{ fill: tokens.muted, fontSize: 11 }}
          />
          <Tooltip
            cursor={{ fill: tokens.grid, fillOpacity: 0.45 }}
            content={<VizTooltip format={(value) => `${value.toFixed(0)} min`} />}
          />
          <Bar dataKey="minutes" name="Downtime" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((entry) => (
              // Planned stops are excluded from availability - shown recessive so
              // the eye lands on the losses that actually cost output.
              <Cell
                key={entry.name}
                fill={entry.planned ? tokens.axis : tokens.series[0]}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
