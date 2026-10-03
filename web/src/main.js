import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './style.css'
import { formatHour, tractColor, validateHours, createPlayback } from './hours.js'
import { createRescueModel, formatClosing } from './rescue.js'

const triangleBounds = [[35.68, -79.08], [36.08, -78.48]]
const map = L.map('map', { zoomControl: false, preferCanvas: true }).setView([35.6, -79.8], 7)
L.control.zoom({ position: 'bottomright' }).addTo(map)
map.createPane('sites')
map.getPane('sites').style.zIndex = 450
const status = document.querySelector('#map-status')
let tileFailed = false
let loaded = false
function showStatus(message) {
  status.hidden = false
  status.textContent = message
}
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).on('tileerror', () => {
  tileFailed = true
  if (loaded) showStatus('Some background tiles could not load. Tracts and sites are still available.')
}).addTo(map)

const hour = document.querySelector('#hour')
const playButton = document.querySelector('#play')
let hourlyData
let mapLayers
let rescueModel
let currentScenario
let selectedCount = 0
let locating = false
let userPoint
let userMarker
const siteLayers = new Map()
const typeLabels = { library: 'Library', hospital: 'Hospital', community_centre: 'Community center', shelter: 'Shelter' }
const sitePath = id => `${import.meta.env.BASE_URL}sites/${encodeURIComponent(id)}?hour=${hour.value}&staffing=${selectedCount}`

function navigate(path) {
  playback.pause()
  history.pushState({}, '', path)
  renderRoute()
}

function renderRoute() {
  const isSite = location.pathname.startsWith(`${import.meta.env.BASE_URL}sites/`)
  document.querySelector('#site-page').hidden = !isSite
  document.querySelector('#map-page').hidden = isSite
  if (isSite) {
    renderSitePage()
    document.querySelector('#site-title').focus({ preventScroll: true })
    window.scrollTo(0, 0)
  } else {
    document.title = 'Last Door · North Carolina map'
    map.invalidateSize({ pan: false })
  }
}

function renderSitePage() {
  if (!rescueModel || document.querySelector('#site-page').hidden) return
  let id
  try { id = decodeURIComponent(location.pathname.slice(`${import.meta.env.BASE_URL}sites/`.length)) } catch { id = '' }
  const locations = rescueModel.sites.filter(s => s.id === id)
  const site = locations[0]
  const title = document.querySelector('#site-title')
  const facts = document.querySelector('#site-facts')
  facts.replaceChildren()
  document.querySelector('#site-show-map').hidden = !site
  if (!site) {
    title.textContent = 'Site not found'
    document.querySelector('#site-type').textContent = ''
    document.querySelector('#site-detail-note').textContent = 'This site ID is not in the current local dataset.'
    return
  }
  title.textContent = site.name
  document.title = `${site.name} · Last Door`
  document.querySelector('#site-type').textContent = typeLabels[site.type] || site.type
  const baseline = hourlyData?.by_hour[hour.value]
  const impact = rescueModel.siteImpact(id, baseline)
  const chosen = currentScenario?.selectedIds.includes(id)
  const pick = currentScenario?.picks.find(p => p.site_id === id)
  const rows = [
    ['Normal closing time', formatClosing(site.close_hour)],
    ['Hours source', site.hours_source === 'default' ? 'Default closing time (unverified)' : site.hours_source === 'osm' ? 'OpenStreetMap' : 'NC OneMap'],
    ['At the selected hour', `${formatHour(Number(hour.value))} · ${chosen ? 'Kept open in this scenario' : site.close_hour == null || Number(hour.value) < site.close_hour ? 'Open' : 'Closed'}`],
    [`People within ${rescueModel.radius} miles`, impact.population.toLocaleString('en-US')],
    ['Additional uncovered people this site could cover', baseline ? impact.additional.toLocaleString('en-US') : 'Hourly data unavailable'],
  ]
  if (pick) rows.push(['People added by this rescue pick', pick.people_added.toLocaleString('en-US')])
  rows.push(['Location', locations.map(s => `${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}`).join(' / ')])
  for (const [label, value] of rows) {
    const term = document.createElement('dt'); term.textContent = label
    const description = document.createElement('dd'); description.textContent = value
    facts.append(term, description)
  }
  document.querySelector('#site-detail-note').textContent = 'Population is measured from tract centroids using straight-line distance. Rescue picks add people after earlier picks, so overlapping coverage is counted once.'
  document.querySelector('#site-show-map').onclick = () => {
    navigate(import.meta.env.BASE_URL)
    const bounds = L.latLngBounds(locations.map(s => [s.lat, s.lon]))
    map.fitBounds(bounds.pad(0.1), { maxZoom: 14, padding: [40, 40], animate: false })
  }
}

function renderRecommendations() {
  const list = document.querySelector('#recommendation-list')
  list.replaceChildren()
  document.querySelector('#saved-population').textContent = selectedCount === 0 ? 'Choose buildings to compare the rescue.' :
    `${currentScenario.peopleSaved.toLocaleString('en-US')} people regain coverage · ${currentScenario.picks.length} building${currentScenario.picks.length === 1 ? '' : 's'} selected`
  for (const pick of currentScenario.picks) {
    const site = rescueModel.sites.find(s => s.id === pick.site_id)
    const link = document.createElement('a')
    link.href = sitePath(pick.site_id)
    link.className = 'recommendation-card'
    const name = document.createElement('strong'); name.textContent = site.name
    const gain = document.createElement('span'); gain.textContent = `+${pick.people_added.toLocaleString('en-US')} people · normally ${formatClosing(site.close_hour).toLowerCase()}`
    link.append(name, gain)
    link.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      event.preventDefault(); navigate(link.href)
    })
    list.append(link)
  }
  if (selectedCount && !currentScenario.picks.length) list.textContent = 'No closed buildings add coverage at this hour.'
  else if (currentScenario.picks.length && currentScenario.picks.length < selectedCount) {
    const note = document.createElement('p'); note.className = 'muted'
    note.textContent = `Only ${currentScenario.picks.length} buildings add coverage at this hour.`
    list.append(note)
  }
}

function renderWalk() {
  if (!userPoint || !rescueModel || !currentScenario) return
  const result = document.querySelector('#walk-result')
  const route = rescueModel.walk(userPoint.lat, userPoint.lng, Number(hour.value), currentScenario.selectedIds)
  result.replaceChildren()
  if (!route) { result.textContent = 'No open door is available at this hour.'; return }
  const link = document.createElement('a'); link.href = sitePath(route.site.id); link.textContent = route.site.name
  link.onclick = event => { if (!event.metaKey && !event.ctrlKey) { event.preventDefault(); navigate(link.href) } }
  const details = document.createElement('p')
  details.textContent = `${route.distance.toFixed(2)} miles · about ${Math.ceil(route.minutes)} min walking · arrival ${formatClosing(route.arrivalHour)}`
  const verdict = document.createElement('p')
  verdict.textContent = !route.withinRadius ? `The nearest open door is outside the ${rescueModel.radius}-mile coverage radius.` :
    !route.beforeClose ? `You would arrive after this door closes at ${formatClosing(route.site.close_hour)}.` :
    route.forced ? 'Within reach if this building is kept open as selected.' : route.site.close_hour == null ? 'Within reach; this door stays open.' : `Within reach before closing at ${formatClosing(route.site.close_hour)}.`
  verdict.className = route.withinRadius && route.beforeClose ? 'walk-success' : 'walk-warning'
  const note = document.createElement('p'); note.className = 'muted'; note.textContent = 'Straight-line estimate at 3 mph, not a walking route.'
  result.append(link, details, verdict, note)
}

function choosePoint(latlng) {
  userPoint = latlng
  locating = false
  document.querySelector('#locate').setAttribute('aria-pressed', 'false')
  document.querySelector('#locate').textContent = 'Change my point on the map'
  document.querySelector('#map').classList.remove('choosing-location')
  if (userMarker) userMarker.setLatLng(latlng)
  else userMarker = L.circleMarker(latlng, { pane: 'sites', radius: 7, color: '#1d4ed8', weight: 3, fillColor: '#fff', fillOpacity: 1 }).addTo(map).bindTooltip('You are here')
  renderWalk()
}
map.on('click', event => { if (locating) choosePoint(event.latlng) })
document.querySelector('#locate').onclick = () => {
  playback.pause()
  locating = !locating
  document.querySelector('#locate').setAttribute('aria-pressed', String(locating))
  document.querySelector('#locate').textContent = locating ? 'Cancel choosing a point' : 'I am here · choose on map'
  document.querySelector('#map').classList.toggle('choosing-location', locating)
  if (locating) document.querySelector('#walk-result').textContent = 'Click any point on the map to place yourself.'
  else renderWalk()
}
document.querySelector('#staffing').addEventListener('change', event => {
  selectedCount = Number(event.target.value)
  renderHour(Number(hour.value))
})
document.querySelector('#back-to-map').onclick = event => { event.preventDefault(); navigate(import.meta.env.BASE_URL) }
window.addEventListener('popstate', renderRoute)
function renderHour(value) {
  hour.value = value
  const label = formatHour(value)
  document.querySelector('#hour-value').value = label
  hour.setAttribute('aria-valuetext', label)
  if (!hourlyData) return
  currentScenario = rescueModel.scenario(hourlyData.by_hour[value], selectedCount)
  const snapshot = currentScenario
  for (const [id, { layer }] of mapLayers) {
    layer.setStyle({ fillColor: tractColor(snapshot.tracts[id]), fillOpacity: 0.65 })
  }
  document.querySelector('#uncovered-population').textContent = snapshot.uncovered_population.toLocaleString('en-US')
  document.querySelector('#impact-hour').textContent = label
  for (const [id, markers] of siteLayers) {
    const chosen = currentScenario.selectedIds.includes(id)
    for (const marker of markers) {
      marker.setStyle({ radius: chosen ? 8 : 3.5, color: chosen ? '#854d0e' : '#fff', weight: chosen ? 3 : 1, fillColor: chosen ? '#facc15' : '#b51f2b' })
      if (chosen) marker.bringToFront()
    }
  }
  renderRecommendations()
  renderWalk()
  renderSitePage()
}
const playback = createPlayback(renderHour, {
  onPlaying(playing) {
    playButton.textContent = playing ? 'Pause' : '▶ Play 4–7 PM'
    playButton.setAttribute('aria-pressed', String(playing))
  },
})
hour.addEventListener('input', () => {
  playback.pause()
  renderHour(Number(hour.value))
})
playButton.addEventListener('click', () => playback.isPlaying() ? playback.pause() : playback.play())
document.addEventListener('visibilitychange', () => { if (document.hidden) playback.pause() })

async function readCollection(name, types) {
  const response = await fetch(`${import.meta.env.BASE_URL}${name}.geojson`)
  if (!response.ok) throw new Error(`${name} request returned ${response.status}`)
  const collection = await response.json()
  if (collection.type !== 'FeatureCollection' || !collection.features?.length ||
      collection.features.some(f => !types.includes(f.geometry?.type) || !f.properties?.id || !f.properties?.name)) {
    throw new Error(`Invalid ${name} collection`)
  }
  return collection
}

function popupTitle(text) {
  const title = document.createElement('strong')
  title.textContent = text
  return title
}

async function loadMap() {
  try {
    const [tracts, sites] = await Promise.all([
      readCollection('tracts', ['Polygon', 'MultiPolygon']),
      readCollection('sites', ['Point']),
    ])
    const picker = document.querySelector('#tract-picker')
    const layers = new Map()
    let selectedLayer
    function select(feature, layer) {
      if (selectedLayer) selectedLayer.setStyle({ weight: 0.7, color: '#676c70' })
      selectedLayer = layer
      layer.setStyle({ weight: 2.5, color: '#22272b' })
      layer.bringToFront()
      document.querySelector('#selected-name').textContent = `${feature.properties.name} · ${feature.properties.id}`
      picker.value = feature.properties.id
    }
    const tractLayer = L.geoJSON(tracts, {
      style: { color: '#676c70', weight: 0.7, fillColor: '#92979c', fillOpacity: 0.38 },
      onEachFeature(feature, layer) {
        layer.bindPopup(popupTitle(`${feature.properties.name} · ${feature.properties.id}`))
        layer.on('click', event => { if (locating) { choosePoint(event.latlng); L.DomEvent.stopPropagation(event); } else select(feature, layer) })
        layers.set(feature.properties.id, { feature, layer })
      },
    }).addTo(map)
    mapLayers = layers
    const options = document.createDocumentFragment()
    for (const feature of [...tracts.features].sort((a, b) => a.properties.name.localeCompare(b.properties.name, 'en', { numeric: true }) || a.properties.id.localeCompare(b.properties.id))) {
      const option = document.createElement('option')
      option.value = feature.properties.id
      option.textContent = `${feature.properties.name} · ${feature.properties.id}`
      options.append(option)
    }
    picker.append(options)
    picker.disabled = false
    picker.addEventListener('change', () => {
      const entry = layers.get(picker.value)
      if (!entry) return
      select(entry.feature, entry.layer)
      map.fitBounds(entry.layer.getBounds(), { maxZoom: 13, padding: [35, 35] })
      entry.layer.openPopup()
    })
    L.geoJSON(sites, {
      pane: 'sites',
      pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {
        pane: 'sites', radius: 3.5, color: '#fff', weight: 1, fillColor: '#b51f2b', fillOpacity: 0.9,
      }),
      onEachFeature(feature, layer) {
        const id = feature.properties.id
        if (!siteLayers.has(id)) siteLayers.set(id, [])
        siteLayers.get(id).push(layer)
        layer.bindTooltip(feature.properties.name)
        layer.on('click', event => {
          if (locating) choosePoint(event.latlng)
          else navigate(sitePath(id))
          L.DomEvent.stopPropagation(event)
        })
      },
    }).addTo(map)
    document.querySelector('#tract-count').textContent = tracts.features.length.toLocaleString('en-US')
    document.querySelector('#site-count').textContent = sites.features.length.toLocaleString('en-US')
    const stateButton = document.querySelector('#view-state')
    const triangleButton = document.querySelector('#view-triangle')
    stateButton.disabled = triangleButton.disabled = false
    stateButton.addEventListener('click', () => map.fitBounds(tractLayer.getBounds(), { padding: [20, 20], animate: false }))
    triangleButton.addEventListener('click', () => map.fitBounds(triangleBounds, { padding: [20, 20], animate: false }))
    map.invalidateSize({ pan: false })
    map.fitBounds(tractLayer.getBounds(), { padding: [20, 20], animate: false })
    loaded = true
    status.hidden = !tileFailed
    if (tileFailed) showStatus('Some background tiles could not load. Tracts and sites are still available.')
    try {
      const response = await fetch(`${import.meta.env.BASE_URL}hours.json`)
      if (!response.ok) throw new Error(`Hourly data request returned ${response.status}`)
      hourlyData = validateHours(await response.json(), tracts.features)
      rescueModel = createRescueModel(tracts.features, sites.features, hourlyData.radius_miles)
      hour.disabled = playButton.disabled = false
      document.querySelector('#staffing').disabled = false
      document.querySelector('#locate').disabled = false
      document.querySelector('#hour-note').textContent = 'Play shows how access changes from 4 PM to 7 PM.'
      document.querySelector('#impact-note').textContent = 'Computed from local hourly data.'
      const query = new URLSearchParams(location.search)
      selectedCount = [0, 1, 3, 5].includes(Number(query.get('staffing'))) ? Number(query.get('staffing')) : 0
      document.querySelector(`input[name="staffing"][value="${selectedCount}"]`).checked = true
      const requestedHour = Number(query.get('hour'))
      renderHour(hourlyData.hours.includes(requestedHour) ? requestedHour : 14)
    } catch (error) {
      document.querySelector('#hour-note').textContent = 'Hourly data unavailable · playback disabled'
      document.querySelector('#impact-note').textContent = 'Could not load matching hours.json data. Tracts remain unscored.'
      console.error('Hourly coverage:', error)
    }
    if (!rescueModel) rescueModel = createRescueModel(tracts.features, sites.features, 3)
    renderRoute()
  } catch (error) {
    showStatus('Could not load the local tract and site files. Run npm run sync:data, then refresh.')
    console.error('NC map:', error)
  }
}

loadMap()
new ResizeObserver(() => map.invalidateSize({ pan: false })).observe(document.querySelector('#map'))
