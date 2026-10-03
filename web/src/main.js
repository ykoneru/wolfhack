import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './style.css'

const map = L.map('map', { zoomControl: false }).setView([35.88, -78.83], 10)
L.control.zoom({ position: 'bottomright' }).addTo(map)

const status = document.querySelector('#map-status')
const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map)
tiles.on('tileerror', () => {
  status.hidden = false
  status.textContent = 'Some background tiles could not load. Sample tracts are still available.'
})

const hour = document.querySelector('#hour')
hour.addEventListener('input', () => {
  const label = `${Number(hour.value) - 12}:00 PM`
  document.querySelector('#hour-value').value = label
  hour.setAttribute('aria-valuetext', label)
  // Step 2: the slider only updates its label; no scoring, filtering, or API requests.
})

async function loadSample() {
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}sample/tracts.geojson`)
    if (!response.ok) throw new Error(`Sample request returned ${response.status}`)
    const sample = await response.json()
    if (sample.type !== 'FeatureCollection' || sample.features?.length !== 5) {
      throw new Error('Expected the five-tract sample FeatureCollection')
    }
    const buttons = new Map()
    let selectedLayer
    function select(feature, layer) {
      if (selectedLayer) selectedLayer.setStyle({ weight: 2, color: '#50565c' })
      selectedLayer = layer
      layer.setStyle({ weight: 3, color: '#22272b' })
      layer.bringToFront()
      document.querySelector('#selected-name').textContent = feature.properties.name
      for (const [id, button] of buttons) {
        button.setAttribute('aria-pressed', String(id === feature.properties.id))
      }
    }
    L.geoJSON(sample, {
      style: { color: '#50565c', weight: 2, fillColor: '#92979c', fillOpacity: 0.65 },
      onEachFeature(feature, layer) {
        const title = document.createElement('strong')
        title.textContent = feature.properties.name
        layer.bindPopup(title)
        layer.on('click', () => select(feature, layer))
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'tract-button'
        button.textContent = feature.properties.name.replace(/^Sample /, '')
        button.setAttribute('aria-pressed', 'false')
        button.addEventListener('click', () => {
          select(feature, layer)
          map.fitBounds(layer.getBounds(), { maxZoom: 13, padding: [60, 60] })
          layer.openPopup()
        })
        buttons.set(feature.properties.id, button)
        document.querySelector('#tract-list').append(button)
      },
    }).addTo(map)
    document.querySelector('#tract-count').textContent = '05'
    if (status.textContent === 'Loading sample tracts…') status.hidden = true
  } catch (error) {
    status.hidden = false
    status.textContent = 'Could not load the five sample tracts. Refresh the page to try again.'
    console.error('Sample map:', error)
  }
}

loadSample()
let initialView = true
new ResizeObserver(() => {
  map.invalidateSize({ pan: false })
  if (initialView) {
    map.fitBounds([[35.68, -79.08], [36.08, -78.48]], { padding: [25, 25] })
    initialView = false
  }
}).observe(document.querySelector('#map'))
