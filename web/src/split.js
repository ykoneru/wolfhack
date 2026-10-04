// Shared formatting and colour rules for the house-or-lot map.

// How far a tract's median land share sits from the county's, in percent.
// Sky is more structure, gold is more land. Neither is a warning.
export const SCALE = [
  { limit: -15, color: '#0369a1', label: 'Mostly structure' },
  { limit: -5, color: '#38bdf8', label: 'More structure' },
  { limit: 5, color: '#4a4a4a', label: 'Near the county typical' },
  { limit: 20, color: '#c9a227', label: 'More land' },
  { limit: Infinity, color: '#e8d48b', label: 'Mostly land' },
]

export const NO_DATA_COLOR = '#6b7280'

export const SHARE_RAMP = ['#0369a1', '#38bdf8', '#c9a227', '#e8d48b']

function mixHex(left, right, amount) {
  const parse = (hex) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ]
  const a = parse(left)
  const b = parse(right)
  const t = Math.max(0, Math.min(1, amount))
  const channel = (index) => Math.round(a[index] + (b[index] - a[index]) * t)
  return `#${[channel(0), channel(1), channel(2)].map((value) => value.toString(16).padStart(2, '0')).join('')}`
}

export function shareRange(shares) {
  const values = shares.filter((value) => value != null)
  if (!values.length) return { min: 0, max: 1 }
  return { min: Math.min(...values), max: Math.max(...values) }
}

export function shareColor(share, range) {
  if (share === null || share === undefined || !range) return NO_DATA_COLOR
  const span = range.max - range.min || 1
  const t = Math.max(0, Math.min(1, (share - range.min) / span))
  const scaled = t * (SHARE_RAMP.length - 1)
  const index = Math.min(SHARE_RAMP.length - 2, Math.floor(scaled))
  return mixHex(SHARE_RAMP[index], SHARE_RAMP[index + 1], scaled - index)
}

export const VERDICT_COLOR = {
  house: '#38bdf8',
  lot: '#c9a227',
  teardown: '#a78bfa',
}

export function tractColor(relativeToCounty) {
  if (relativeToCounty === null || relativeToCounty === undefined) return NO_DATA_COLOR
  return SCALE.find((step) => relativeToCounty < step.limit).color
}

export function tractLabel(relativeToCounty) {
  if (relativeToCounty === null || relativeToCounty === undefined) return 'Too few homes to grade'
  return SCALE.find((step) => relativeToCounty < step.limit).label
}

export function dollars(value) {
  if (value === null || value === undefined) return '—'
  const rounded = Math.round(value)
  const sign = rounded < 0 ? '-' : ''
  return `${sign}$${Math.abs(rounded).toLocaleString('en-US')}`
}

export function shareText(value) {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

export function percentText(value) {
  if (value === null || value === undefined) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

export function saleDateText(iso) {
  if (!iso) return '—'
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function verdictSentence(detail) {
  const share = shareText(detail.land_share)
  if (detail.verdict === 'teardown') {
    return `Teardown watch. Land is ${share} of the split and the house was built in ${detail.year_built}.`
  }
  if (detail.verdict === 'lot') {
    return `This purchase is mostly land. Land is ${share} of the county split.`
  }
  return `This purchase is mostly the house. Land is ${share} of the split, so the structure is the bigger piece.`
}

export function hotspotSentence(payload) {
  const top = payload?.neighborhoods?.[0]
  if (!top) return 'No neighborhood has enough homes to rank.'
  return (
    `${top.name} has the highest typical land share at ${shareText(top.median_land_share)}. ` +
    `That is where the typical purchase is more land than the rest of Wake.`
  )
}

export function barHeights(cities) {
  if (!cities || !cities.length) return []
  const shares = cities.map((row) => row.median_land_share)
  const low = Math.min(...shares)
  const high = Math.max(...shares)
  const span = high - low || 1
  return cities.map((row) => ({
    ...row,
    height: Math.round(25 + 75 * ((row.median_land_share - low) / span)),
  }))
}
