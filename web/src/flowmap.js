export function categoryFor(score) {
  if (score <= 25) return 'Quiet'
  if (score <= 45) return 'Light'
  if (score <= 65) return 'Moderate'
  if (score <= 80) return 'Busy'
  return 'Very Busy'
}

const STOPS = [
  [0, [215, 232, 223]],
  [25, [143, 191, 168]],
  [45, [230, 195, 92]],
  [65, [224, 122, 61]],
  [80, [194, 59, 59]],
  [100, [142, 30, 30]],
]

export function activityColor(score) {
  const value = Math.max(0, Math.min(100, score))
  let lower = STOPS[0]
  let upper = STOPS[STOPS.length - 1]
  for (let index = 0; index < STOPS.length - 1; index += 1) {
    if (value >= STOPS[index][0] && value <= STOPS[index + 1][0]) {
      lower = STOPS[index]
      upper = STOPS[index + 1]
      break
    }
  }
  const span = upper[0] - lower[0] || 1
  const mix = (value - lower[0]) / span
  const channel = index => Math.round(lower[1][index] + (upper[1][index] - lower[1][index]) * mix)
  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`
}

export function milesBetween(lat1, lon1, lat2, lon2) {
  const radius = 3958.7613
  const toRad = value => value * Math.PI / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * radius * Math.asin(Math.sqrt(a))
}

export function leaveAt(arrivalHour, travelMinutes) {
  const total = arrivalHour * 60 - travelMinutes
  if (total < 8 * 60) return null
  const hour = Math.floor(total / 60)
  const minute = total % 60
  const suffix = hour < 12 ? 'AM' : 'PM'
  const shown = hour % 12 || 12
  return `${shown}:${String(minute).padStart(2, '0')} ${suffix}`
}

export function categoryShift(earlier, later) {
  if (earlier.category === later.category) {
    return `${earlier.label} and ${later.label} are both ${earlier.category}. The score moves from ${earlier.score} to ${later.score}.`
  }
  return `${earlier.label} is ${earlier.category} (${earlier.score}). ${later.label} is ${later.category} (${later.score}).`
}

export function clockLabel(hour) {
  const suffix = hour < 12 ? 'AM' : 'PM'
  const shown = hour === 0 || hour === 12 ? 12 : hour > 12 ? hour - 12 : hour
  return `${shown}:00 ${suffix}`
}

export function visitFits(hour, openHour, closeHour, minimumMinutes) {
  if (hour < openHour) return false
  return hour * 60 + minimumMinutes <= closeHour * 60
}

export function bestHour(series, place, earliest, latest, minimumMinutes) {
  let chosen = null
  for (let hour = earliest; hour <= latest; hour += 1) {
    const block = series[String(hour)]
    if (!block || !visitFits(hour, place.open, place.close, minimumMinutes)) continue
    if (!chosen || block.score < chosen.score) chosen = { hour, score: block.score, category: block.category }
  }
  return chosen
}

export function explanation(facts) {
  const sentences = []
  if (facts.destinationsBest < facts.destinationsNow) sentences.push('The destination score is lower then.')
  if (facts.commuteBest < facts.commuteNow) sentences.push('The weekday commute score is lower then.')
  if (facts.hoursSource === 'default') sentences.push('The hours used here are the category default, not a confirmed schedule.')
  else if (facts.hoursSource === 'area') sentences.push('This score is for the tract, not one business schedule.')
  else sentences.push('The place is still inside the hours recorded for it.')
  if (Math.abs(facts.weatherBest - facts.weatherNow) < 1) sentences.push('The weather adjustment barely changes.')
  return `Estimated activity near ${facts.name} is ${facts.bestScore} at ${facts.bestLabel}, compared with ${facts.currentScore} at ${facts.currentLabel}. ${sentences.join(' ')}`
}
