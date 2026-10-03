/** Shared scoring rules for Last Door. Keep these in sync with pipeline/rules.py. */

export const RADIUS_MILES = 3
export const EXPOSED_BURDEN_MIN = 0.4
export const HEAT_FLOOR_F = 75
export const HEAT_SPAN_F = 35
export const AQI_SPAN = 200
export const WALK_MPH = 3
export const HOURS = [14, 15, 16, 17, 18, 19, 20]
export const BURDEN_WEIGHTS = { vulnerability: 0.5, heat: 0.35, air: 0.15 }

export function clamp(value, low = 0, high = 1) {
  return Math.max(low, Math.min(high, value))
}

export function heatRisk(temperatureF) {
  return clamp((temperatureF - HEAT_FLOOR_F) / HEAT_SPAN_F)
}

export function airRisk(aqi) {
  return clamp(aqi / AQI_SPAN)
}

export function vulnerability(shareAge65Plus, povertyRate, shareHouseholdsNoVehicle) {
  return (shareAge65Plus + povertyRate + shareHouseholdsNoVehicle) / 3
}

export function burden(shareAge65Plus, povertyRate, shareHouseholdsNoVehicle, temperatureF, aqi) {
  return (
    BURDEN_WEIGHTS.vulnerability * vulnerability(shareAge65Plus, povertyRate, shareHouseholdsNoVehicle) +
    BURDEN_WEIGHTS.heat * heatRisk(temperatureF) +
    BURDEN_WEIGHTS.air * airRisk(aqi)
  )
}

export function haversineMiles(lat1, lon1, lat2, lon2) {
  const radius = 3958.7613
  const phi1 = (lat1 * Math.PI) / 180
  const phi2 = (lat2 * Math.PI) / 180
  const dPhi = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLon / 2) ** 2
  return 2 * radius * Math.asin(Math.sqrt(a))
}

export function isOpen(site, hour, committedSiteIds = []) {
  if (committedSiteIds.includes(site.id)) return true
  if (site.close_hour == null) return true
  return hour < site.close_hour
}

export function isExposed(burdenValue) {
  return burdenValue >= EXPOSED_BURDEN_MIN
}
