export function assessmentSummary(properties) {
  if (!properties.enough_sales || !Number.isFinite(properties.median_ratio)) {
    return {
      headline: 'Not enough sales to compare',
      comparison: 'At least 15 qualifying sales are needed for a reliable area comparison.',
      basis: `${properties.sales ?? 0} qualifying home sales in 2024`,
    }
  }
  const relative = properties.relative_to_county
  const comparison = !Number.isFinite(relative)
    ? 'County comparison unavailable.'
    : Math.abs(relative) < 0.05
      ? 'In line with Wake County’s typical assessment level.'
      : `${Math.abs(relative).toFixed(1)}% ${relative > 0 ? 'higher' : 'lower'} than Wake County’s typical assessment level.`
  return {
    headline: `Assessed at ${(properties.median_ratio * 100).toFixed(1)}% of sale price`,
    comparison,
    basis: `Median across ${(properties.sales ?? 0).toLocaleString('en-US')} qualifying home sales in 2024`,
  }
}

export function tractSummaryCard(properties, places = [], onDetails) {
  const card = document.createElement('div')
  card.className = 'tract-tooltip-content'
  const summary = assessmentSummary(properties)
  const rows = [
    ['strong', 'tract-tooltip-title', places.length ? places.join(' / ') : 'Wake County area'],
    ['span', 'tract-tooltip-location', `${properties.name} · Census statistical area`],
    ...(places.length ? [['span', 'tract-tooltip-source', 'Location names from recorded sale addresses']] : []),
    ['strong', 'tract-tooltip-assessment', summary.headline],
    ['span', 'tract-tooltip-comparison', summary.comparison],
    ['span', 'tract-tooltip-basis', summary.basis],
  ]
  for (const [tag, className, value] of rows) {
    const element = document.createElement(tag)
    element.className = className
    element.textContent = value
    card.append(element)
  }
  const details = document.createElement('button')
  details.type = 'button'
  details.className = 'tract-tooltip-action'
  details.textContent = 'View area details'
  details.addEventListener('click', onDetails)
  card.append(details)
  return card
}
