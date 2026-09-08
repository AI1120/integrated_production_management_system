export const num = (value: number | null | undefined, digits = 0): string =>
  value == null ? '-' : value.toLocaleString(undefined, { maximumFractionDigits: digits })

/** Quantities: whole numbers stay clean, fractional ones keep up to 3 decimals. */
export const qty = (value: number | null | undefined): string => {
  if (value == null) return '-'
  return Number.isInteger(value) ? value.toLocaleString() : num(value, 3)
}

export const money = (value: number | null | undefined): string =>
  value == null ? '-' : value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const pct = (fraction: number | null | undefined, digits = 1): string =>
  fraction == null ? '-' : `${(fraction * 100).toFixed(digits)}%`

export const dateTime = (value: string | null | undefined): string =>
  !value ? '-' : new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export const dateOnly = (value: string | null | undefined): string =>
  !value ? '-' : new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' })

export const timeOnly = (value: string | null | undefined): string =>
  !value ? '-' : new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

export const duration = (minutes: number | null | undefined): string => {
  if (minutes == null) return '-'
  if (minutes < 60) return `${Math.round(minutes)} min`
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}

/** "12 min ago" - used on live boards where the absolute time adds nothing. */
export const since = (value: string | null | undefined): string => {
  if (!value) return '-'
  const minutes = (Date.now() - new Date(value).getTime()) / 60000
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${Math.round(minutes)} min ago`
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}h ago`
  return `${Math.floor(minutes / 1440)}d ago`
}

export const titleCase = (value: string): string =>
  value.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())

/** Local datetime string in the format <input type="datetime-local"> expects. */
export const toLocalInput = (date: Date): string => {
  const offset = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

/** Role names for people to read. QC is an acronym, not a word. */
const ROLE_LABELS: Record<string, string> = {
  ADMIN: 'Admin',
  PLANNER: 'Planner',
  OPERATOR: 'Operator',
  QC: 'QC',
  WAREHOUSE: 'Warehouse',
  VIEWER: 'Viewer',
}

export const roleLabel = (role: string): string => ROLE_LABELS[role] ?? titleCase(role)
