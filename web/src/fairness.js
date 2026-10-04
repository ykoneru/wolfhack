// Shared formatting and colour rules for the assessment map.

// How far a tract's median sales ratio sits from the county's, in percent.
// Emerald means assessed lighter than the county norm, red means heavier.
export const SCALE = [
  { limit: -4, color: '#0f766e', label: 'Assessed much lighter' },
  { limit: -1.5, color: '#10b981', label: 'Lighter' },
  { limit: 1.5, color: '#4a4a4a', label: 'At the county norm' },
  { limit: 4, color: '#e5484d', label: 'Heavier' },
  { limit: Infinity, color: '#a2191f', label: 'Assessed much heavier' },
]

export const NO_DATA_COLOR = '#161616'

export function tractColor(relativeToCounty) {
  if (relativeToCounty === null || relativeToCounty === undefined) return NO_DATA_COLOR
  return SCALE.find((step) => relativeToCounty < step.limit).color
}

export function tractLabel(relativeToCounty) {
  if (relativeToCounty === null || relativeToCounty === undefined) return 'Too few sales to grade'
  return SCALE.find((step) => relativeToCounty < step.limit).label
}

export function dollars(value) {
  if (value === null || value === undefined) return '—'
  const rounded = Math.round(value)
  const sign = rounded < 0 ? '-' : ''
  return `${sign}$${Math.abs(rounded).toLocaleString('en-US')}`
}

export function ratioText(value) {
  if (value === null || value === undefined) return '—'
  return value.toFixed(3)
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

// A measure passes when it falls inside the range the IAAO publishes for it.
export function withinStandard(value, [low, high]) {
  return value >= low && value <= high
}

export function standardRow(name, value, range, format) {
  return {
    name,
    value: format(value),
    range: `${format(range[0])}–${format(range[1])}`,
    passes: withinStandard(value, range),
  }
}

// The sentence a homeowner actually wants: am I assessed above or below the
// county norm, and by how much.
export function gapSentence(gap) {
  if (gap.difference === 0) return 'This assessment sits exactly at the county norm.'
  const direction = gap.difference > 0 ? 'above' : 'below'
  return `Assessed ${dollars(Math.abs(gap.difference))} ${direction} the county norm, ${percentText(gap.percent)}.`
}

// The gradient across price bands, stated as the spread between the cheapest
// and most expensive band.
export function tiltSummary(bands) {
  if (!bands || bands.length < 2) return null
  const cheapest = bands[0]
  const priciest = bands[bands.length - 1]
  const spread = (cheapest.median_ratio - priciest.median_ratio) * 100
  return {
    cheapest: cheapest.median_ratio,
    priciest: priciest.median_ratio,
    spread: Number(spread.toFixed(1)),
    regressive: spread > 0,
  }
}

export function inheritSentence(payload) {
  if (!payload || payload.median_ratio === null || payload.median_ratio === undefined) {
    return `No 2024 sales closed at or under ${dollars(payload?.budget)}.`
  }
  const direction = payload.heavier_than_county ? 'heavier' : 'lighter'
  return (
    `At ${dollars(payload.budget)}, buyers in 2024 inherited a typical ratio of ` +
    `${ratioText(payload.median_ratio)}, ${direction} than the county's ` +
    `${ratioText(payload.county_median_ratio)}. That number stays until ${payload.next_revaluation}.`
  )
}

export function barHeights(bands) {
  if (!bands || !bands.length) return []
  const ratios = bands.map((band) => band.median_ratio)
  const low = Math.min(...ratios)
  const high = Math.max(...ratios)
  const span = high - low || 1
  // Floor at a quarter height so the shortest bar is still a readable block.
  return bands.map((band) => ({
    ...band,
    height: Math.round(25 + 75 * ((band.median_ratio - low) / span)),
  }))
}
