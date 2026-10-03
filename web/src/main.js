import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './style.css'

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
hour.addEventListener('input', () => {
  const label = `${Number(hour.value) - 12}:00 PM`
  document.querySelector('#hour-value').value = label
  hour.setAttribute('aria-valuetext', label)
  // Step 4: all shapes and sites remain visible; scoring comes later.
})

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
        layer.on('click', () => select(feature, layer))
        layers.set(feature.properties.id, { feature, layer })
      },
    }).addTo(map)
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
    const typeLabels = { library: 'Library', hospital: 'Hospital', community_centre: 'Community center', shelter: 'Shelter' }
    L.geoJSON(sites, {
      pane: 'sites',
      pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {
        pane: 'sites', radius: 3.5, color: '#fff', weight: 1, fillColor: '#b51f2b', fillOpacity: 0.9,
      }),
      onEachFeature(feature, layer) {
        const content = document.createElement('div')
        content.append(popupTitle(feature.properties.name))
        const type = document.createElement('div')
        type.textContent = typeLabels[feature.properties.type] || feature.properties.type
        content.append(type)
        layer.bindPopup(content)
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
  } catch (error) {
    showStatus('Could not load the local tract and site files. Run npm run sync:data, then refresh.')
    console.error('NC map:', error)
  }
}

loadMap()
new ResizeObserver(() => map.invalidateSize({ pan: false })).observe(document.querySelector('#map'))
