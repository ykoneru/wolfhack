export const TRACT_COLORS = {
  uncovered: '#dc2626',
  covered: '#0d9488',
  neutral: '#92979c',
}

export function formatHour(hour) {
  return `${hour - 12}:00 PM`
}

export function tractColor(tract) {
  if (tract.uncovered) return TRACT_COLORS.uncovered
  if (tract.exposed && tract.covered) return TRACT_COLORS.covered
  return TRACT_COLORS.neutral
}

export function validateHours(document, features) {
  if (!Number.isFinite(document.radius_miles) || document.radius_miles <= 0) {
    throw new Error('Hourly data must specify a positive coverage radius')
  }
  const required = [14, 15, 16, 17, 18, 19, 20]
  if (!Array.isArray(document.hours) || required.some(h => !document.hours.includes(h))) {
    throw new Error('Hourly data must contain every hour from 2 PM through 8 PM')
  }
  const ids = new Set(features.map(f => f.properties.id))
  for (const h of required) {
    const snapshot = document.by_hour?.[h]
    if (!snapshot || !Number.isSafeInteger(snapshot.uncovered_population) || snapshot.uncovered_population < 0 ||
        Object.keys(snapshot.tracts ?? {}).length !== ids.size) {
      throw new Error(`Invalid population or tract count for hour ${h}`)
    }
    let population = 0
    for (const feature of features) {
      const tract = snapshot.tracts[feature.properties.id]
      if (!tract || ['covered', 'exposed', 'uncovered'].some(key => typeof tract[key] !== 'boolean') ||
          tract.uncovered !== (tract.exposed && !tract.covered)) {
        throw new Error(`Invalid coverage for ${feature.properties.id} at hour ${h}`)
      }
      if (tract.uncovered) population += feature.properties.population
    }
    if (population !== snapshot.uncovered_population) {
      throw new Error(`Population total does not match the tracts for hour ${h}`)
    }
  }
  return document
}

export function createPlayback(render, { schedule = setInterval, cancel = clearInterval, onPlaying = () => {} } = {}) {
  let timer = null
  function pause() {
    if (timer !== null) cancel(timer)
    timer = null
    onPlaying(false)
  }
  function play() {
    pause()
    let hour = 16
    render(hour)
    onPlaying(true)
    timer = schedule(() => {
      render(++hour)
      if (hour === 19) pause()
    }, 1600)
  }
  return { play, pause, isPlaying: () => timer !== null }
}
