import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './style.css'
import { activityColor, bestHour, categoryShift, clockLabel, explanation, leaveAt, milesBetween, visitFits } from './flowmap.js'

const API = 'http://127.0.0.1:8000'
const hourInput = document.querySelector('#hour')
const hourLabel = document.querySelector('#hour-label')
const playButton = document.querySelector('#play')
const searchInput = document.querySelector('#search')
const searchResults = document.querySelector('#search-results')

const CAMPUS = { lat: 35.7847, lon: -78.6821, label: 'NC State' }
const state = {
  activity: null,
  places: [],
  byPlace: new Map(),
  tracts: new Map(),
  layers: new Map(),
  selected: null,
  tractId: null,
  timer: null,
  planReady: false,
  origin: { ...CAMPUS },
  trip: null,
  routeLayer: null,
  originMarker: null,
  pickingOrigin: false,
}

function selectedHour() {
  return Number(hourInput.value)
}

function windowSettings() {
  return {
    earliest: Number(document.querySelector('#earliest').value),
    latest: Number(document.querySelector('#latest').value),
    minimum: Number(document.querySelector('#minimum').value),
  }
}

function styleFor(tractId) {
  const block = state.activity.tracts[tractId]?.[String(selectedHour())]
  const score = block ? block.score : 0
  const selected = tractId === state.tractId
  return {
    color: selected ? '#ffffff' : '#1f1f1f',
    weight: selected ? 2.5 : 0.6,
    fillColor: activityColor(score),
    fillOpacity: 0.72,
  }
}

function paint() {
  hourLabel.textContent = clockLabel(selectedHour())
  for (const [tractId, layer] of state.layers) layer.setStyle(styleFor(tractId))
  if (state.selected) {
    renderChoice(state.selected.name, state.selected.hours_source, state.selected.open, state.selected.close, state.selected.tract_id)
  } else if (state.tractId) {
    const tract = state.tracts.get(state.tractId)
    renderChoice(tract.name, 'area', 0, 24, tract.id)
  }
}

function renderSeries(tractId) {
  const chart = document.querySelector('#chart')
  const series = state.activity.tracts[tractId]
  chart.innerHTML = Object.entries(series).map(([hour, block]) => {
    const height = Math.max(4, Math.round(block.score))
    const current = Number(hour) === selectedHour() ? ' current' : ''
    return `<div class="bar${current}" style="height:${height}%" title="${clockLabel(Number(hour))} ${block.score}"><span>${clockLabel(Number(hour)).replace(':00 ', '')}</span></div>`
  }).join('')
}

function renderFactors(block) {
  document.querySelector('#factors').innerHTML = [
    ['Population', block.population],
    ['Commute', block.commute],
    ['Destinations', block.destinations],
    ['Connectivity', block.roads],
    ['Weather', block.weather],
  ].map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')
}

function renderChoice(name, hoursSource, openHour, closeHour, tractId) {
  const series = state.activity.tracts[tractId]
  const current = series[String(selectedHour())]
  const settings = windowSettings()
  const chosen = bestHour(series, { open: openHour, close: closeHour }, settings.earliest, settings.latest, settings.minimum)
  document.querySelector('#current-score').textContent = `${Math.round(current.score)}`
  document.querySelector('#current-category').textContent = `${current.category} at ${clockLabel(selectedHour())}`
  document.querySelector('#meter-fill').style.width = `${current.score}%`
  renderFactors(current)
  renderSeries(tractId)
  if (!chosen) {
    document.querySelector('#best-time').textContent = 'No usable time'
    document.querySelector('#best-score').textContent = 'Nothing in that window leaves enough time before closing.'
    document.querySelector('#explanation').textContent = ''
    return null
  }
  const best = series[String(chosen.hour)]
  document.querySelector('#best-time').textContent = clockLabel(chosen.hour)
  const reduction = current.score <= 0 ? 0 : Math.round(((current.score - best.score) / current.score) * 100)
  const compared = `${best.score} / 100 — ${best.category}`
  document.querySelector('#best-score').textContent = reduction > 0
    ? `${compared}. About ${reduction}% lower than ${clockLabel(selectedHour())}.`
    : `${compared}. ${clockLabel(selectedHour())} is outside the window that still gets you there and back.`
  document.querySelector('#explanation').textContent = explanation({
    name,
    bestScore: best.score,
    bestLabel: clockLabel(chosen.hour),
    currentScore: current.score,
    currentLabel: clockLabel(selectedHour()),
    destinationsBest: best.destinations,
    destinationsNow: current.destinations,
    commuteBest: best.commute,
    commuteNow: current.commute,
    weatherBest: best.weather,
    weatherNow: current.weather,
    hoursSource,
  })
  const five = series['17']
  const eight = series['20']
  const card = (block, label) => `<div style="background:${activityColor(block.score)}"><span>${label}</span><strong>${Math.round(block.score)}</strong><em>${block.category}</em></div>`
  document.querySelector('#compare').innerHTML = card(five, '5:00 PM') + card(eight, '8:00 PM')
  document.querySelector('#shift').textContent = categoryShift(
    { label: '5:00 PM', score: five.score, category: five.category },
    { label: '8:00 PM', score: eight.score, category: eight.category },
  )
  updateLeaveBy(chosen.hour)
  return chosen
}

function renderPlace(place) {
  state.selected = place
  state.tractId = place.tract_id
  const tract = state.tracts.get(place.tract_id)
  document.querySelector('#place-category').textContent = place.category.replaceAll('_', ' ').toUpperCase()
  document.querySelector('#place-name').textContent = place.name
  const hoursPrefix = place.hours_source === 'default' ? 'Estimated hours ' : 'Recorded hours '
  document.querySelector('#place-hours').textContent = `${hoursPrefix}${clockLabel(place.open)}–${place.close >= 24 ? 'midnight' : clockLabel(place.close)}`
  renderChoice(place.name, place.hours_source, place.open, place.close, place.tract_id)
  document.querySelector('#context').textContent = tract
    ? `${tract.population.toLocaleString('en-US')} people live in this tract. ${tract.workers.toLocaleString('en-US')} workers. ${Math.round(tract.morning_departure_share * 100)}% leave for work between 7 and 9am on a weekday.`
    : ''
  paintSelection()
  loadSeries(place.tract_id)
}

function renderTract(tract) {
  state.selected = null
  state.tractId = tract.id
  document.querySelector('#place-category').textContent = 'AREA'
  document.querySelector('#place-name').textContent = tract.name
  document.querySelector('#place-hours').textContent = 'An area stays available all day. Pick a destination for opening hours.'
  renderChoice(tract.name, 'area', 0, 24, tract.id)
  document.querySelector('#context').textContent = `${tract.population.toLocaleString('en-US')} people. ${tract.destination_count.toLocaleString('en-US')} destinations. ${tract.road_count.toLocaleString('en-US')} major-road segments and bus stops.`
  paintSelection()
  loadSeries(tract.id)
}

function paintSelection() {
  for (const [tractId, layer] of state.layers) layer.setStyle(styleFor(tractId))
}

async function loadSeries(tractId) {
  const note = document.querySelector('#series-source')
  try {
    const response = await fetch(`${API}/series?tract_id=${encodeURIComponent(tractId)}`)
    const payload = await response.json()
    note.textContent = payload.source === 'tiger' ? 'This weekday series is stored in Tiger Data.' : 'This weekday series is read from the saved activity file.'
  } catch {
    note.textContent = 'This weekday series is read from the saved activity file.'
  }
}

async function hear() {
  const place = state.selected
  if (!place) return
  const settings = windowSettings()
  const response = await fetch(`${API}/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      place_id: place.id,
      hour: selectedHour(),
      earliest: settings.earliest,
      latest: settings.latest,
      minimum_visit_minutes: settings.minimum,
    }),
  })
  const payload = await response.json()
  if (!response.ok) {
    document.querySelector('#explanation').textContent = payload.error || 'The explanation is unavailable.'
    return
  }
  document.querySelector('#explanation').textContent = payload.reply
  const audio = await fetch(`${API}/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: payload.reply }),
  })
  if (!audio.ok) return
  const url = URL.createObjectURL(await audio.blob())
  const player = new Audio(url)
  player.onended = () => URL.revokeObjectURL(url)
  player.play()
}

function updateLeaveBy(arrivalHour) {
  const leave = document.querySelector('#leave-by')
  if (!state.trip || arrivalHour == null) {
    leave.textContent = ''
    return
  }
  const departure = leaveAt(arrivalHour, state.trip.minutes)
  leave.textContent = departure
    ? `Leave ${state.origin.label} by ${departure} to arrive at ${clockLabel(arrivalHour)}.`
    : `The drive is longer than the time before ${clockLabel(arrivalHour)}.`
}

function setOrigin(lat, lon, label) {
  state.origin = { lat, lon, label }
  document.querySelector('#origin-label').textContent = `From ${label}`
  if (state.originMarker) state.originMarker.remove()
  state.originMarker = L.circleMarker([lat, lon], {
    radius: 8,
    color: '#10b981',
    fillColor: '#030303',
    fillOpacity: 1,
    weight: 3,
  }).addTo(map).bindPopup(label)
  if (state.selected) drawRoute(state.selected, false)
}

async function drawRoute(place, fit) {
  const card = document.querySelector('#route-card')
  card.hidden = false
  document.querySelector('#route-summary').textContent = 'Finding the road route…'
  const response = await fetch(
    `${API}/route?from_lat=${state.origin.lat}&from_lon=${state.origin.lon}&to_lat=${place.lat}&to_lon=${place.lon}`,
  )
  const payload = await response.json()
  if (!response.ok) {
    document.querySelector('#route-summary').textContent = 'The route is unavailable.'
    return
  }
  if (state.routeLayer) state.routeLayer.remove()
  state.routeLayer = L.geoJSON(payload.geometry, { style: { color: '#10b981', weight: 5, opacity: 0.95 } }).addTo(map)
  state.trip = payload
  const via = payload.source === 'road network' ? 'by road' : 'in a straight-line estimate'
  document.querySelector('#route-summary').textContent = `${payload.minutes} min · ${payload.miles} mi ${via}`
  const chosen = bestHour(
    state.activity.tracts[place.tract_id],
    place,
    windowSettings().earliest,
    windowSettings().latest,
    windowSettings().minimum,
  )
  updateLeaveBy(chosen && chosen.hour)
  if (fit && state.routeLayer.getBounds().isValid()) map.fitBounds(state.routeLayer.getBounds(), { padding: [28, 28] })
}

function planErrand() {
  const note = document.querySelector('#errand-note')
  const category = document.querySelector('#errand').value
  const backBy = Number(document.querySelector('#class-hour').value)
  const minimum = windowSettings().minimum
  const nearby = state.places
    .filter(place => place.named && place.category === category)
    .map(place => ({ place, miles: milesBetween(state.origin.lat, state.origin.lon, place.lat, place.lon) }))
    .filter(item => item.miles <= 8)
    .sort((a, b) => a.miles - b.miles)
    .slice(0, 40)
  let chosen = null
  for (const item of nearby) {
    const travelMin = Math.max(1, Math.round(item.miles / 25 * 60))
    const series = state.activity.tracts[item.place.tract_id]
    if (!series) continue
    for (let hour = 8; hour < backBy; hour += 1) {
      if (hour * 60 + minimum + travelMin > backBy * 60) continue
      if (!visitFits(hour, item.place.open, item.place.close, minimum)) continue
      const block = series[String(hour)]
      if (!chosen || block.score < chosen.score) chosen = { place: item.place, hour, score: block.score, category: block.category }
    }
  }
  if (!chosen) {
    note.textContent = 'No stop of that type fits the drive, the visit, and the trip back before class.'
    return
  }
  const travelMin = Math.max(1, Math.round(milesBetween(state.origin.lat, state.origin.lon, chosen.place.lat, chosen.place.lon) / 25 * 60))
  let latest = chosen.hour
  for (let hour = 8; hour < backBy; hour += 1) {
    if (hour * 60 + minimum + travelMin <= backBy * 60 && visitFits(hour, chosen.place.open, chosen.place.close, minimum)) latest = hour
  }
  document.querySelector('#earliest').value = '8'
  document.querySelector('#latest').value = String(latest)
  note.textContent = `${chosen.place.name} at ${clockLabel(chosen.hour)} is ${chosen.category} (${chosen.score}). That leaves time to get back before ${clockLabel(backBy)}.`
  selectPlace(chosen.place, true)
}

function selectPlace(place, fly) {
  searchResults.innerHTML = ''
  renderPlace(place)
  drawRoute(place, fly)
}

const map = L.map('map')
const canvas = L.canvas({ padding: 0.5 })
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }).addTo(map)

const [activity, placeDocument, tractDocument] = await Promise.all([
  fetch('/activity.json').then(response => response.json()),
  fetch('/places.json').then(response => response.json()),
  fetch('/wake-tracts.geojson').then(response => response.json()),
])
state.activity = activity
state.places = placeDocument.places
for (const place of state.places) state.byPlace.set(place.id, place)
for (const feature of tractDocument.features) state.tracts.set(feature.properties.id, feature.properties)

const tractsLayer = L.geoJSON(tractDocument, {
  style: feature => styleFor(feature.properties.id),
  onEachFeature(feature, layer) {
    state.layers.set(feature.properties.id, layer)
    layer.on('click', () => {
      if (state.pickingOrigin) return
      renderTract(feature.properties)
    })
  },
}).addTo(map)
map.fitBounds(tractsLayer.getBounds(), { padding: [12, 12] })

for (const place of state.places) {
  const marker = L.circleMarker([place.lat, place.lon], {
    renderer: canvas,
    radius: place.named ? 4 : 3,
    color: '#030303',
    weight: 1,
    fillColor: '#030303',
    fillOpacity: 0.8,
  })
  marker.bindPopup(`<strong>${place.name}</strong><br>${place.category}`)
  marker.on('click', event => {
    L.DomEvent.stopPropagation(event)
    selectPlace(place, false)
  })
  marker.addTo(map)
}

hourInput.addEventListener('input', paint)
for (const id of ['earliest', 'latest', 'minimum']) document.querySelector(`#${id}`).addEventListener('change', paint)
playButton.addEventListener('click', () => {
  if (state.timer) {
    clearInterval(state.timer)
    state.timer = null
    playButton.textContent = 'Play'
    return
  }
  playButton.textContent = 'Stop'
  state.timer = setInterval(() => {
    const next = selectedHour() >= 22 ? 8 : selectedHour() + 1
    hourInput.value = String(next)
    paint()
    if (next === 22) {
      clearInterval(state.timer)
      state.timer = null
      playButton.textContent = 'Play'
    }
  }, 900)
})
searchInput.addEventListener('input', () => {
  const query = searchInput.value.trim().toLowerCase()
  searchResults.innerHTML = ''
  if (query.length < 2) return
  for (const place of state.places.filter(item => item.named && item.name.toLowerCase().includes(query)).slice(0, 8)) {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = `${place.name} · ${place.category}`
    button.addEventListener('click', () => {
      searchInput.value = place.name
      selectPlace(place, true)
    })
    searchResults.append(button)
  }
})
document.querySelector('#search-form').addEventListener('submit', event => event.preventDefault())
document.querySelector('#hear').addEventListener('click', hear)
document.querySelector('#save-plan').addEventListener('click', async () => {
  const place = state.selected
  const chosen = place && bestHour(
    state.activity.tracts[place.tract_id],
    place,
    windowSettings().earliest,
    windowSettings().latest,
    windowSettings().minimum,
  )
  if (!chosen) return
  const response = await fetch(`${API}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ place_id: place.id, hour: chosen.hour }),
  })
  const payload = await response.json()
  const note = document.querySelector('#plan-note')
  if (!response.ok) {
    note.textContent = payload.error || 'The plan was not recorded.'
    document.querySelector('#save-plan').hidden = true
    return
  }
  note.innerHTML = `Recorded <a href="${payload.explorer_url}">${payload.memo}</a>.`
})

try {
  const ready = await fetch(`${API}/plan`)
  const payload = await ready.json()
  state.planReady = Boolean(payload.ready)
  document.querySelector('#save-plan').hidden = !state.planReady
} catch {
  state.planReady = false
}

map.on('click', event => {
  if (!state.pickingOrigin) return
  state.pickingOrigin = false
  document.querySelector('#set-start').setAttribute('aria-pressed', 'false')
  setOrigin(event.latlng.lat, event.latlng.lng, 'Chosen start')
})
document.querySelector('#locate').addEventListener('click', () => {
  if (!navigator.geolocation) return
  navigator.geolocation.getCurrentPosition(
    position => setOrigin(position.coords.latitude, position.coords.longitude, 'Your location'),
    () => { document.querySelector('#origin-label').textContent = 'From NC State' },
  )
})
document.querySelector('#set-start').addEventListener('click', () => {
  state.pickingOrigin = !state.pickingOrigin
  document.querySelector('#set-start').setAttribute('aria-pressed', String(state.pickingOrigin))
})
for (const button of document.querySelectorAll('.demo')) {
  button.addEventListener('click', () => {
    const place = state.places.find(item => item.name === button.dataset.place)
    if (place) selectPlace(place, true)
  })
}
document.querySelector('#plan-errand').addEventListener('click', planErrand)
setOrigin(CAMPUS.lat, CAMPUS.lon, CAMPUS.label)

const opening = state.places.find(place => place.name === 'Spring Rolls Asian Bistro and Sushi Bar')
  || state.byPlace.get(activity.demo_place_id)
if (opening) selectPlace(opening, true)
