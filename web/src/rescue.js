import { haversineMiles, isOpen, WALK_MPH } from './rules.js'

export function formatClosing(hour) {
  if (hour == null) return 'Open 24 hours'
  if (hour === 0) return 'Closed today'
  const minutes = Math.round(hour * 60)
  const h = Math.floor(minutes / 60) % 24
  return `${h % 12 || 12}:${String(minutes % 60).padStart(2, '0')} ${h >= 12 ? 'PM' : 'AM'}`
}

export function createRescueModel(tractFeatures, siteFeatures, radius) {
  const sites = siteFeatures.map(feature => ({ ...feature.properties,
    lon: feature.geometry.coordinates[0], lat: feature.geometry.coordinates[1] }))
  const reach = new Map()
  for (const site of sites) {
    if (!reach.has(site.id)) reach.set(site.id, new Map())
    const rows = reach.get(site.id)
    for (const feature of tractFeatures) {
      const p = feature.properties
      const [lon, lat] = p.centroid
      const distance = haversineMiles(lat, lon, site.lat, site.lon)
      if (distance <= radius && (!rows.has(p.id) || distance < rows.get(p.id).distance)) {
        rows.set(p.id, { distance, population: p.population })
      }
    }
  }

  function scenario(snapshot, count) {
    const picks = snapshot.recommendations?.[String(count)] ?? []
    const rows = { ...snapshot.tracts }
    const saved = new Set()
    let peopleSaved = 0
    for (const pick of picks) {
      if (!reach.has(pick.site_id)) throw new Error('Recommendation references an unknown site')
      for (const [id, info] of reach.get(pick.site_id)) {
        const row = rows[id]
        if (row.uncovered && !saved.has(id)) {
          saved.add(id)
          peopleSaved += info.population
        }
        if (!row.covered || row.distance_miles == null || info.distance < row.distance_miles) {
          rows[id] = { ...row, covered: true, uncovered: false,
            nearest_site_id: pick.site_id, distance_miles: info.distance }
        }
      }
    }
    return { tracts: rows, uncovered_population: snapshot.uncovered_population - peopleSaved,
      peopleSaved, picks, selectedIds: picks.map(p => p.site_id) }
  }

  function siteImpact(id, snapshot) {
    let population = 0
    let additional = 0
    for (const [tractId, info] of reach.get(id) ?? []) {
      population += info.population
      if (snapshot?.tracts[tractId]?.uncovered) additional += info.population
    }
    return { population, additional }
  }

  function walk(lat, lon, hour, selectedIds = []) {
    let nearest = null
    for (const site of sites) {
      if (!isOpen(site, hour, selectedIds)) continue
      const distance = haversineMiles(lat, lon, site.lat, site.lon)
      if (!nearest || distance < nearest.distance) nearest = { site, distance }
    }
    if (!nearest) return null
    const arrivalHour = hour + nearest.distance / WALK_MPH
    const forced = selectedIds.includes(nearest.site.id)
    return { ...nearest, minutes: nearest.distance / WALK_MPH * 60, arrivalHour,
      withinRadius: nearest.distance <= radius,
      beforeClose: forced || nearest.site.close_hour == null || arrivalHour < nearest.site.close_hour,
      forced }
  }
  return { scenario, siteImpact, walk, sites, radius }
}
