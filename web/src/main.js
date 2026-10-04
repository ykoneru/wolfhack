import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import './style.css'
import { dismissHint, initHint } from './hint.js'
import { closeAsk, closeDetails, openDetails } from './panel.js'
import {
  askAboutLabel,
  normalizeQuestion,
  prettyPlace,
  suggestedQuestions,
  toParagraphs,
  trimHistory,
} from './conversation.js'
import { cautionFlags } from './caution.js'
import { ASK_COPY, COMPARE, DISCLAIMER, FOR_SALE, LOT_PREVIEW, MAP_VIEW, SEARCH_COPY } from './config.js'
import {
  NO_DATA_COLOR,
  VERDICT_COLOR,
  dollars,
  percentText,
  shareColor,
  shareRange,
  shareText,
  verdictSentence,
} from './split.js'
import { defaultSalePrefs, parseSaleNumber, saleCountLabel, saleMatches } from './sale.js'
import {
  compareSubjectName,
  compareViewHtml,
  countySubject,
  exportCompareFilename,
  exportCompareMarkup,
  exportFilename,
  exportSplitMarkup,
  homeSubject,
  isCountyCompareQuery,
  matchNeighborhoods,
  neighborhoodSubject,
} from './tools.js'

const API = 'http://127.0.0.1:8000'
const WAKE_CENTER = [35.79, -78.65]

const map = L.map('map', { center: WAKE_CENTER, zoom: 10, zoomControl: false, attributionControl: true })
map.createPane('tracts')
map.getPane('tracts').style.zIndex = 400
map.createPane('homes')
map.getPane('homes').style.zIndex = 450
map.createPane('listings')
map.getPane('listings').style.zIndex = 460
map.attributionControl.setPrefix(false)
let wakeBounds = L.latLngBounds(MAP_VIEW.wakeBounds)
let framedWake = false
applyWakeFrame(true)
new ResizeObserver(() => {
  map.invalidateSize()
  applyWakeFrame()
}).observe(document.querySelector('#map'))
const lotPreviewHost = document.querySelector('#lot-preview')
if (lotPreviewHost) {
  new ResizeObserver(() => {
    if (lotPreview && lotPreviewHost.offsetWidth) lotPreview.invalidateSize()
  }).observe(lotPreviewHost)
}
// Standard OSM tiles, darkened in CSS so the basemap sits behind the data
// instead of competing with it.
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap',
  maxZoom: 19,
}).addTo(map)

let county = null
let tractLayer = null
let tractGeojson = null
let salesLayer = null
let listingLayer = null
let listingRows = []
let listingFetchedAt = null
let listingWindowDays = 30
let forSaleOn = false
let homeMarker = null
let parcelLayer = null
let lotPreview = null
let shareScale = { min: 0, max: 1 }
let selectedPin = null
let selectedAddress = null
let selectedNeighborhood = null
let selectedHome = null
let compareA = null
let compareB = null
let lastQuery = ''

function text(id, value) {
  document.querySelector(id).textContent = value
}

function show(id, visible) {
  document.querySelector(id).hidden = !visible
}

function applyWakeFrame(force = false) {
  if (!wakeBounds || !map.getSize().x) return
  if (framedWake && !force) return
  map.fitBounds(wakeBounds, {
    paddingTopLeft: MAP_VIEW.paddingTopLeft,
    paddingBottomRight: MAP_VIEW.paddingBottomRight,
    animate: false,
  })
  map.setMaxBounds(wakeBounds.pad(MAP_VIEW.maxBoundsPad))
  const fitted = map.getBoundsZoom(wakeBounds, false, MAP_VIEW.paddingTopLeft)
  if (Number.isFinite(fitted)) map.setMinZoom(Math.max(MAP_VIEW.minZoom, fitted))
  framedWake = true
}

function frameMap(bounds) {
  wakeBounds = bounds
  framedWake = false
  applyWakeFrame(true)
}

function renderMapLegend(range) {
  let box = document.querySelector('#map-legend')
  if (!box) {
    box = document.createElement('aside')
    box.id = 'map-legend'
    box.className = 'map-legend'
    box.setAttribute('aria-label', 'Percent of assessed value in land')
    document.querySelector('#map').appendChild(box)
    L.DomEvent.disableClickPropagation(box)
    L.DomEvent.disableScrollPropagation(box)
  }
  box.innerHTML = `
    <p class="map-legend-title">% of assessed value in land</p>
    <div class="map-legend-bar" aria-hidden="true"></div>
    <div class="map-legend-ticks">
      <span>${shareText(range.min)}</span>
      <span>${shareText((range.min + range.max) / 2)}</span>
      <span>${shareText(range.max)}</span>
    </div>
    <div class="map-legend-swatch"><i></i> Insufficient data</div>`
}

function clearHighlight() {
  if (homeMarker) {
    homeMarker.remove()
    homeMarker = null
  }
  if (parcelLayer) {
    parcelLayer.remove()
    parcelLayer = null
  }
  if (salesLayer) {
    salesLayer.remove()
    salesLayer = null
  }
}

function resetHomePanel() {
  selectedPin = null
  selectedAddress = null
  selectedHome = null
  syncExport()
  paintCompare()
  updateAskContext()
  renderSuggestions()
  show('#home-summary', false)
  text('#home-address', '')
  text('#home-meta', '')
  clearLotPreview()
  show('#ratio-card', false)
  show('#gap-card', false)
  show('#caution-badge', false)
  show('#listing-badge', false)
  show('#result-disclaimer', false)
}

function syncHighlightVisibility() {
  const zoom = map.getZoom()
  if (homeMarker) {
    if (zoom < MAP_VIEW.hideHighlightBelowZoom) homeMarker.remove()
    else if (!map.hasLayer(homeMarker)) homeMarker.addTo(map)
  }
  if (parcelLayer) {
    if (zoom < MAP_VIEW.hideHighlightBelowZoom) parcelLayer.remove()
    else if (!map.hasLayer(parcelLayer)) parcelLayer.addTo(map)
  }
  if (salesLayer) {
    if (forSaleOn || zoom < MAP_VIEW.hidePointsBelowZoom) salesLayer.remove()
    else if (!map.hasLayer(salesLayer)) salesLayer.addTo(map)
  }
  const tractPane = map.getPane('tracts')
  if (tractPane) {
    tractPane.style.pointerEvents = zoom >= MAP_VIEW.hidePointsBelowZoom && salesLayer ? 'none' : ''
  }
}

function clearLotPreview() {
  if (lotPreview) {
    lotPreview.remove()
    lotPreview = null
  }
  const host = document.querySelector('#lot-preview')
  const note = document.querySelector('#lot-preview-note')
  if (host) {
    host.hidden = true
    host.replaceChildren()
  }
  if (note) {
    note.hidden = true
    note.textContent = ''
  }
}

function renderLotPreview(detail) {
  const host = document.querySelector('#lot-preview')
  const note = document.querySelector('#lot-preview-note')
  if (!host || detail.lat == null || detail.lon == null) {
    clearLotPreview()
    return
  }
  clearLotPreview()
  host.hidden = false
  lotPreview = L.map(host, {
    center: [detail.lat, detail.lon],
    zoom: LOT_PREVIEW.zoom,
    zoomControl: false,
    attributionControl: true,
    scrollWheelZoom: false,
  })
  lotPreview.attributionControl.setPrefix(false)
  L.tileLayer(LOT_PREVIEW.tiles, {
    attribution: LOT_PREVIEW.attribution,
    maxZoom: LOT_PREVIEW.zoom,
  }).addTo(lotPreview)
  if (detail.geometry) {
    const outline = L.geoJSON(detail.geometry, {
      style: {
        color: '#ffffff',
        weight: 2,
        fillColor: VERDICT_COLOR[detail.verdict] || '#ffffff',
        fillOpacity: 0.16,
      },
    }).addTo(lotPreview)
    lotPreview.fitBounds(outline.getBounds(), { padding: [14, 14], maxZoom: LOT_PREVIEW.zoom })
  }
  if (note) {
    note.hidden = false
    note.textContent = LOT_PREVIEW.caption
  }
  requestAnimationFrame(() => lotPreview?.invalidateSize())
  window.setTimeout(() => lotPreview?.invalidateSize(), 220)
}

function markParcel(detail) {
  clearHighlight()
  const color = VERDICT_COLOR[detail.verdict] || '#ffffff'
  if (detail.geometry) {
    parcelLayer = L.geoJSON(detail.geometry, {
      style: {
        color: '#ffffff',
        weight: 2,
        fillColor: color,
        fillOpacity: 0.18,
      },
    }).addTo(map)
  }
  homeMarker = L.marker([detail.lat, detail.lon], {
    icon: L.divIcon({
      className: 'home-pin',
      html: `<span class="home-pin-dot" style="background:${color}"></span>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    }),
    keyboard: false,
  })
    .addTo(map)
    .bindPopup(`${detail.address}<br>${detail.verdict_label} · ${shareText(detail.land_share)} land`)
  const target = parcelLayer ? parcelLayer.getBounds() : L.latLngBounds([detail.lat, detail.lon], [detail.lat, detail.lon])
  map.flyToBounds(target.pad(0.4), { maxZoom: MAP_VIEW.flyZoom, duration: 0.6 })
  syncHighlightVisibility()
}

function paintShareMeter(share, verdict) {
  const fill = document.querySelector('#ratio-fill')
  fill.style.width = `${Math.round(Math.max(0, Math.min(1, share)) * 100)}%`
  fill.dataset.state = verdict || (share >= 0.4 ? 'lot' : 'house')
}

function renderHome(detail) {
  selectedPin = detail.pin
  show('#home-summary', true)
  const built = detail.year_built ? `built ${detail.year_built}` : 'year built unknown'
  const area = detail.heated_area ? `${Math.round(detail.heated_area).toLocaleString('en-US')} sq ft` : 'size unknown'
  text('#home-address', detail.address)
  text('#home-meta', `${detail.city} · ${built} · ${area}`)
  const listingBadge = document.querySelector('#listing-badge')
  if (detail.listing?.price) {
    listingBadge.hidden = false
    listingBadge.textContent = `For sale · ${dollars(detail.listing.price)}`
  } else {
    listingBadge.hidden = true
    listingBadge.textContent = ''
  }

  text('#home-ratio', detail.verdict_label)
  document.querySelector('#home-ratio').dataset.state = detail.verdict
  paintShareMeter(detail.land_share, detail.verdict)
  text(
    '#ratio-caption',
    `Land is ${shareText(detail.land_share)} of the split. County typical is ${shareText(county.median_land_share)}.`,
  )
  document.querySelector('#home-figures').innerHTML = [
    ['Land', `${dollars(detail.land)} · ${shareText(detail.land_share)}`],
    ['Building', `${dollars(detail.building)} · ${shareText(1 - detail.land_share)}`],
    ['Total assessed', dollars(detail.assessed)],
    ['Last sale', detail.price ? dollars(detail.price) : '—'],
  ]
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
    .join('')
  show('#ratio-card', true)

  const bits = [verdictSentence(detail), detail.advice]
  if (detail.tract.median_land_share) {
    const versus = detail.versus_tract === null || detail.versus_tract === undefined
      ? ''
      : ` That is ${percentText(detail.versus_tract)} from the tract typical.`
    bits.push(
      `${detail.tract.name} typically sits at ${shareText(detail.tract.median_land_share)} land.${versus}`,
    )
  }
  if (detail.year_built && detail.verdict === 'lot') {
    bits.push(`The house was built in ${detail.year_built}, so this is a newer building on a high-value lot.`)
  }
  document.querySelector('#gap-bits').innerHTML = bits.map((line) => `<p>${line}</p>`).join('')
  show('#gap-card', true)
  const flags = cautionFlags(detail)
  const badge = document.querySelector('#caution-badge')
  if (flags.length) {
    badge.hidden = false
    badge.textContent = flags[0].reason
  } else {
    badge.hidden = true
    badge.textContent = ''
  }
  const note = document.querySelector('#result-disclaimer')
  note.hidden = false
  note.innerHTML = `${DISCLAIMER} <a href="/method.html">Learn more</a>`
  text('#chain-note', '')

  selectedAddress = detail.address
  selectedHome = detail
  syncExport()
  history = []
  updateAskContext()
  renderChat()
  renderSuggestions()

  markParcel(detail)
  loadTract(detail.tract.id, { open: false })
  if (comparePanelOpen()) {
    closeDetails()
    paintCompare()
  } else {
    openDetails()
    renderLotPreview(detail)
  }
}

function renderTract(detail) {
  selectedNeighborhood = detail.name
  updateAskContext()
  renderSuggestions()

  if (salesLayer) salesLayer.remove()
  salesLayer = L.layerGroup(
    detail.points.map((point) =>
      L.circleMarker([point.lat, point.lon], {
        pane: 'homes',
        radius: 6,
        weight: 2,
        color: '#ffffff',
        fillColor: VERDICT_COLOR[point.verdict] || '#8f8f8f',
        fillOpacity: 0.95,
        bubblingMouseEvents: false,
      })
        .bindTooltip(
          `${point.address} · ${point.verdict === 'teardown' ? 'Teardown watch' : point.verdict === 'lot' ? 'Lot' : 'House'}`,
          {
          direction: 'top',
          className: 'map-tooltip',
        })
        .on('click', () => selectParcel(point.pin)),
    ),
  )
  syncHighlightVisibility()
}

async function loadTract(tractId, { open = false } = {}) {
  if (open) dismissHint()
  const response = await fetch(`${API}/tract?id=${tractId}`)
  if (!response.ok) return
  renderTract(await response.json())
}

async function selectParcel(pin) {
  openDetails()
  const response = await fetch(`${API}/parcel?pin=${pin}`)
  if (!response.ok) {
    clearHighlight()
    resetHomePanel()
    setSearchState('error', SEARCH_COPY.error)
    return
  }
  renderHome(await response.json())
  setSearchState('success')
  dismissHint()
}

function tractTooltip(props) {
  if (!props.enough_homes) return `${props.name} · Insufficient data`
  return `${props.name} · ${shareText(props.median_land_share)} land`
}

async function loadTracts() {
  const [geoResponse, landResponse] = await Promise.all([
    fetch('/wake-tracts.geojson'),
    fetch('/land.json'),
  ])
  const geojson = await geoResponse.json()
  const land = landResponse.ok ? await landResponse.json() : { tracts: {} }
  for (const feature of geojson.features) {
    const row = land.tracts?.[feature.properties.id]
    if (!row) continue
    feature.properties.median_land = row.median_land
    feature.properties.median_building = row.median_building
    feature.properties.homes = row.homes
  }
  tractGeojson = geojson
  shareScale = shareRange(
    geojson.features
      .filter((feature) => feature.properties.enough_homes)
      .map((feature) => feature.properties.median_land_share),
  )
  tractLayer = L.geoJSON(geojson, {
    pane: 'tracts',
    style: tractStyle,
    onEachFeature: (feature, layer) => {
      layer.bindTooltip(tractTooltip(feature.properties), { sticky: true, className: 'map-tooltip' })
      layer.on('click', () => loadTract(feature.properties.id))
    },
  })
  frameMap(tractLayer.getBounds())
  tractLayer.addTo(map)
  renderMapLegend(shareScale)
}

function tractStyle(feature) {
  const enough = feature.properties.enough_homes
  const fill = enough ? shareColor(feature.properties.median_land_share, shareScale) : NO_DATA_COLOR
  return {
    color: '#111111',
    weight: 1,
    fillColor: fill,
    fillOpacity: enough ? 0.5 : 0.28,
  }
}

async function loadCounty() {
  county = await (await fetch(`${API}/county`)).json()
}

async function loadListings() {
  const response = await fetch(`${API}/listings`)
  if (!response.ok) return
  const payload = await response.json()
  listingFetchedAt = payload.fetched_at || null
  listingWindowDays = Number(payload.window_days) || 30
  listingRows = (payload.listings || []).filter((row) => row.lat && row.lon)
  if (listingLayer) {
    listingLayer.remove()
    listingLayer = null
  }
  paintSaleCount()
  if (forSaleOn) paintListingLayer()
}

function filteredListings() {
  return saleMatches(listingRows, readSalePrefs())
}

function paintListingLayer() {
  if (listingLayer) {
    listingLayer.remove()
    listingLayer = null
  }
  if (!forSaleOn) return
  const rows = filteredListings()
  if (!rows.length) {
    renderForSaleNote()
    return
  }
  listingLayer = L.layerGroup(
    rows.map((row) =>
      L.circleMarker([row.lat, row.lon], {
        pane: 'listings',
        radius: 5,
        weight: 2,
        color: '#c62828',
        fillColor: '#ffffff',
        fillOpacity: 0.95,
        bubblingMouseEvents: false,
      })
        .bindTooltip(
          `${row.address} · for sale${row.price ? ` · ${dollars(row.price)}` : ''}${
            Number.isFinite(Number(row.land_share)) ? ` · ${shareText(row.land_share)} land` : ''
          }`,
          { direction: 'top', className: 'map-tooltip' },
        )
        .on('click', () => {
          searchInput.value = row.address
          document.querySelector('#search-form').requestSubmit()
        }),
    ),
  ).addTo(map)
  renderForSaleNote()
}

function renderForSaleNote() {
  let box = document.querySelector('#for-sale-note')
  if (!box) {
    box = document.createElement('aside')
    box.id = 'for-sale-note'
    box.className = 'for-sale-note'
    box.setAttribute('aria-live', 'polite')
    document.querySelector('#map').appendChild(box)
    L.DomEvent.disableClickPropagation(box)
  }
  const rows = forSaleOn ? filteredListings() : []
  if (!forSaleOn || !rows.length) {
    box.hidden = true
    box.textContent = ''
    return
  }
  box.hidden = false
  box.textContent = `${rows.length.toLocaleString('en-US')} for sale · listed in the last ${listingWindowDays} days`
}

function setForSale(on) {
  forSaleOn = Boolean(on) && listingRows.length > 0
  const toggle = document.querySelector('#for-sale-toggle')
  if (toggle) {
    toggle.setAttribute('aria-pressed', String(forSaleOn))
    toggle.classList.toggle('rail-active', forSaleOn)
  }
  document.body.classList.toggle('for-sale-on', forSaleOn)
  if (forSaleOn) paintListingLayer()
  else {
    if (listingLayer) {
      listingLayer.remove()
      listingLayer = null
    }
    renderForSaleNote()
  }
  syncHighlightVisibility()
}

const searchInput = document.querySelector('#search')
const searchResults = document.querySelector('#search-results')
const searchSubmit = document.querySelector('.search-submit')
const searchSpinner = document.querySelector('#search-spinner')
const searchStatus = document.querySelector('#search-status')
const searchRetry = document.querySelector('#search-retry')
let searchTimer = null

function setSearchState(state, message = '') {
  document.querySelector('#search-form').dataset.state = state
  searchStatus.dataset.state = state
  searchStatus.textContent = message
  const loading = state === 'loading'
  searchSubmit.disabled = loading
  searchSpinner.hidden = !loading
  searchRetry.hidden = state !== 'error'
}

function renderMatches(matches) {
  searchResults.innerHTML = matches
    .map(
      (match) => `<button type="button" data-pin="${match.pin}" data-address="${match.address}">
        ${match.address}<span class="match-city">${match.city}${match.verdict ? ` · ${match.verdict}` : ''}${match.for_sale ? ' · for sale' : ''}</span>
      </button>`,
    )
    .join('')
}

async function runSearch(query, { submit = false } = {}) {
  if (submit) dismissHint()
  lastQuery = query
  const trimmed = query.trim()
  if (trimmed.length < 3) {
    searchResults.innerHTML = ''
    setSearchState('idle')
    return []
  }
  setSearchState('loading')
  try {
    const response = await fetch(`${API}/search?q=${encodeURIComponent(trimmed)}`)
    if (!response.ok) throw new Error('search failed')
    const matches = (await response.json()).matches || []
    if (!matches.length) {
      searchResults.innerHTML = ''
      if (submit) {
        clearHighlight()
        resetHomePanel()
      }
      setSearchState('empty', SEARCH_COPY.notFound)
      return []
    }
    renderMatches(matches)
    if (matches.length === 1 && submit) {
      searchInput.value = matches[0].address
      searchResults.innerHTML = ''
      await selectParcel(matches[0].pin)
      return matches
    }
    setSearchState('success', matches.length > 1 ? SEARCH_COPY.pick : '')
    return matches
  } catch {
    searchResults.innerHTML = ''
    if (submit) {
      clearHighlight()
      resetHomePanel()
    }
    setSearchState('error', SEARCH_COPY.error)
    return []
  }
}

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => runSearch(searchInput.value), 180)
})

document.querySelector('#search-form').addEventListener('submit', (event) => {
  event.preventDefault()
  runSearch(searchInput.value, { submit: true })
})

searchRetry.addEventListener('click', () => {
  runSearch(lastQuery || searchInput.value, { submit: true })
})

searchResults.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-pin]')
  if (!button) return
  searchResults.innerHTML = ''
  searchInput.value = button.dataset.address
  selectParcel(button.dataset.pin)
})

document.querySelectorAll('.demo').forEach((button) => {
  button.addEventListener('click', async () => {
    searchInput.value = button.dataset.query
    const matches = await runSearch(button.dataset.query, { submit: true })
    if (matches.length > 1) {
      searchInput.value = matches[0].address
      searchResults.innerHTML = ''
      selectParcel(matches[0].pin)
    }
  })
})

map.on('zoomend', syncHighlightVisibility)

const chat = document.querySelector('#chat')
const suggestions = document.querySelector('#suggestions')
const suggestPrompt = document.querySelector('#suggest-prompt')
const askForm = document.querySelector('#ask-form')
const questionInput = document.querySelector('#question')
const askButton = document.querySelector('#ask')
const askError = document.querySelector('#ask-error')
const askErrorText = document.querySelector('#ask-error-text')
const retryAsk = document.querySelector('#retry-ask')
let history = []
let pending = false
let lastFailedQuestion = ''

function compareAskSubject(item) {
  if (!item) return null
  if (item.kind === 'home' && item.pin) return { kind: 'home', pin: item.pin }
  if (item.kind === 'neighborhood') return { kind: 'neighborhood', id: item.id || item.tract?.id || '' }
  if (item.kind === 'county') return { kind: 'county' }
  return null
}

function compareAskPayload() {
  if (!comparePanelOpen() || (!compareA && !compareB)) return null
  return {
    left: compareAskSubject(compareA),
    right: compareAskSubject(compareB),
  }
}

function askContext() {
  if (comparePanelOpen() && (compareA || compareB)) {
    return {
      compare: true,
      leftName: compareSubjectName(compareA),
      rightName: compareSubjectName(compareB),
    }
  }
  return { address: selectedAddress, neighborhood: selectedNeighborhood }
}

function updateAskContext() {
  const line = document.querySelector('#ask-context')
  if (line) line.textContent = askAboutLabel(askContext())
  if (typeof renderSuggestions === 'function') renderSuggestions()
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function growQuestion() {
  questionInput.style.height = 'auto'
  const line = 24
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, line * 4)}px`
}

function syncSend() {
  askButton.disabled = pending || !normalizeQuestion(questionInput.value)
}

function setAskError(message) {
  askError.hidden = !message
  askErrorText.textContent = message || ''
}

function renderChat(waiting) {
  const turns = history.map((turn) => {
    const body = toParagraphs(turn.text)
      .map((line) => `<p>${escapeHtml(line)}</p>`)
      .join('')
    const avatar =
      turn.role === 'assistant' ? '<span class="ask-avatar" aria-hidden="true">H</span>' : ''
    return `<div class="turn turn-${turn.role}">
      ${avatar}
      <div class="bubble">${body}</div>
    </div>`
  })
  if (waiting) {
    turns.push(`<div class="turn turn-assistant pending">
      <span class="ask-avatar" aria-hidden="true">H</span>
      <div class="bubble"><span class="typing" aria-label="Thinking"></span></div>
    </div>`)
  }
  chat.innerHTML = turns.join('')
  chat.scrollTop = chat.scrollHeight
}

function renderSuggestions() {
  suggestions.innerHTML = suggestedQuestions(askContext())
    .map((question) => `<button type="button" class="suggestion">${escapeHtml(question)}</button>`)
    .join('')
  const compact = history.length > 0
  suggestions.classList.toggle('is-compact', compact)
  suggestPrompt.hidden = compact
}

async function sendQuestion(raw) {
  const question = normalizeQuestion(raw)
  if (!question || pending) return
  lastFailedQuestion = ''
  setAskError('')
  questionInput.value = ''
  growQuestion()
  pending = true
  history.push({ role: 'you', text: question })
  syncSend()
  renderChat(true)
  renderSuggestions()
  try {
    const response = await fetch(`${API}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pin: selectedPin || '',
        question,
        history: trimHistory(history.slice(0, -1)),
        compare: compareAskPayload(),
      }),
    })
    const payload = await response.json()
    if (!response.ok && !payload.reply) throw new Error('ask failed')
    const reply = payload.reply || payload.error || 'That did not go through. Try again.'
    history.push({ role: 'assistant', text: reply })
    renderChat()
  } catch {
    lastFailedQuestion = question
    setAskError(ASK_COPY.error)
    renderChat()
  } finally {
    pending = false
    syncSend()
    questionInput.focus()
  }
}

askForm.addEventListener('submit', (event) => {
  event.preventDefault()
  sendQuestion(questionInput.value)
})

questionInput.addEventListener('input', () => {
  growQuestion()
  syncSend()
})

questionInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (!askButton.disabled) askForm.requestSubmit()
  }
})

suggestions.addEventListener('click', (event) => {
  const button = event.target.closest('.suggestion')
  if (button) sendQuestion(button.textContent)
})

retryAsk.addEventListener('click', () => {
  if (lastFailedQuestion) sendQuestion(lastFailedQuestion)
})

updateAskContext()
syncSend()

const saveButton = document.querySelector('#save-ratio')
saveButton.addEventListener('click', async () => {
  if (!selectedPin) return
  saveButton.disabled = true
  try {
    const response = await fetch(`${API}/appeal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: selectedPin }),
    })
    const payload = await response.json()
    document.querySelector('#chain-note').innerHTML = payload.explorer_url
      ? `Recorded as <code>${payload.memo}</code>. <a href="${payload.explorer_url}" target="_blank" rel="noreferrer">View on Solana devnet</a>.`
      : payload.error
  } finally {
    saveButton.disabled = false
  }
})

const comparePanel = document.querySelector('#compare-panel')
const compareSearch = document.querySelector('#compare-search')
const compareResults = document.querySelector('#compare-results')
const compareStatus = document.querySelector('#compare-status')
const exportButton = document.querySelector('#export-split')
let compareTimer = null
let compareSearchGen = 0

function comparePanelOpen() {
  const panel = document.querySelector('#compare-panel')
  return Boolean(panel && !panel.hidden)
}

function compareLeft() {
  return compareA
}

function canExportCompare() {
  return comparePanelOpen() && Boolean(compareA && compareB)
}

function syncExport() {
  exportButton.disabled = !(canExportCompare() || (!comparePanelOpen() && selectedHome))
}

function placeCompare(item) {
  if (!compareLeft()) compareA = item
  else compareB = item
}

function comparePlaceholder() {
  if (!compareA) return COMPARE.placeholder
  if (!compareB) return COMPARE.placeholderSecond
  return COMPARE.placeholderMore
}

function paintCompare() {
  if (!comparePanel) return
  compareSearch.placeholder = comparePlaceholder()
  document.querySelector('#compare-body').innerHTML = compareViewHtml(compareLeft(), compareB, county)
  syncExport()
  updateAskContext()
}

function openCompare() {
  closeDetails()
  closeSale()
  comparePanel.hidden = false
  document.body.classList.add('compare-open')
  const toggle = document.querySelector('#compare-homes')
  toggle.setAttribute('aria-expanded', 'true')
  toggle.classList.add('rail-active')
  paintCompare()
  compareSearch.focus()
}

function closeCompare() {
  compareA = null
  compareB = null
  cancelCompareSearch()
  compareSearch.value = ''
  compareResults.innerHTML = ''
  compareStatus.textContent = ''
  paintCompare()
  comparePanel.hidden = true
  document.body.classList.remove('compare-open')
  const toggle = document.querySelector('#compare-homes')
  toggle.setAttribute('aria-expanded', 'false')
  toggle.classList.remove('rail-active')
  syncExport()
}

const salePanel = document.querySelector('#for-sale-panel')
const saleShow = document.querySelector('#sale-show')
const salePriceMin = document.querySelector('#sale-price-min')
const salePriceMax = document.querySelector('#sale-price-max')
const saleLandMin = document.querySelector('#sale-land-min')
const saleLandMax = document.querySelector('#sale-land-max')

function salePanelOpen() {
  return Boolean(salePanel && !salePanel.hidden)
}

function readSalePrefs() {
  let priceMin = parseSaleNumber(salePriceMin?.value)
  let priceMax = parseSaleNumber(salePriceMax?.value)
  if (priceMin != null && priceMax != null && priceMin > priceMax) {
    ;[priceMin, priceMax] = [priceMax, priceMin]
  }
  let landMin = parseSaleNumber(saleLandMin?.value)
  let landMax = parseSaleNumber(saleLandMax?.value)
  if (landMin != null) landMin = Math.max(0, Math.min(100, landMin))
  if (landMax != null) landMax = Math.max(0, Math.min(100, landMax))
  if (landMin != null && landMax != null && landMin > landMax) {
    ;[landMin, landMax] = [landMax, landMin]
  }
  return { priceMin, priceMax, landMin, landMax }
}

function paintSaleCount() {
  if (!saleShow) return
  if (!listingRows.length) {
    saleShow.textContent = FOR_SALE.empty
    saleShow.disabled = true
    return
  }
  const count = filteredListings().length
  saleShow.textContent = saleCountLabel(count)
  saleShow.disabled = count === 0
}

function resetSaleControls() {
  const defaults = defaultSalePrefs()
  if (salePriceMin) salePriceMin.value = defaults.priceMin ?? ''
  if (salePriceMax) salePriceMax.value = defaults.priceMax ?? ''
  if (saleLandMin) saleLandMin.value = defaults.landMin ?? ''
  if (saleLandMax) saleLandMax.value = defaults.landMax ?? ''
  paintSaleCount()
}

function openSale() {
  closeAsk()
  closeCompare()
  if (salePanel) salePanel.hidden = false
  document.body.classList.add('sale-open')
  paintSaleCount()
  setForSale(true)
}

function closeSale() {
  if (salePanel) salePanel.hidden = true
  document.body.classList.remove('sale-open')
  setForSale(false)
}

function localCompareChoices(query) {
  const choices = []
  if (isCountyCompareQuery(query)) {
    const item = countySubject(county)
    if (item) choices.push({ kind: 'county', label: item.label, note: 'County typical land and building' })
  }
  for (const props of matchNeighborhoods(tractGeojson?.features, query)) {
    choices.push({
      kind: 'neighborhood',
      id: props.id,
      label: props.name,
      note: props.enough_homes === false ? 'Insufficient data' : 'Neighborhood typical',
    })
  }
  return choices
}

function renderCompareChoices(local, matches) {
  const localButtons = local.map((choice) => {
    if (choice.kind === 'county') {
      return `<button type="button" data-kind="county">${choice.label}<span class="match-city">${choice.note}</span></button>`
    }
    return `<button type="button" data-kind="neighborhood" data-tract-id="${choice.id}">${choice.label}<span class="match-city">${choice.note}</span></button>`
  })
  const homeButtons = matches.map(
    (match) => `<button type="button" data-kind="home" data-pin="${match.pin}" data-address="${match.address}">
      ${match.address}<span class="match-city">${match.city || ''}${match.verdict ? ` · ${match.verdict}` : ''}${match.for_sale ? ' · for sale' : ''}</span>
    </button>`,
  )
  compareResults.innerHTML = [...localButtons, ...homeButtons].join('')
}

function cancelCompareSearch() {
  clearTimeout(compareTimer)
  compareSearchGen += 1
}

async function runCompareSearch(query, { submit = false } = {}) {
  const trimmed = query.trim()
  const gen = ++compareSearchGen
  if (trimmed.length < 3) {
    compareResults.innerHTML = ''
    compareStatus.textContent = ''
    return []
  }
  const local = localCompareChoices(trimmed)
  compareStatus.textContent = 'Searching…'
  try {
    const response = await fetch(`${API}/search?q=${encodeURIComponent(trimmed)}`)
    if (gen !== compareSearchGen) return []
    if (!response.ok) throw new Error('search failed')
    const matches = (await response.json()).matches || []
    if (!local.length && !matches.length) {
      compareResults.innerHTML = ''
      compareStatus.textContent = SEARCH_COPY.notFound
      return []
    }
    renderCompareChoices(local, matches)
    if (submit && local.length === 1 && !matches.length) {
      compareResults.innerHTML = ''
      selectCompareChoice(local[0])
      return local
    }
    if (submit && matches.length === 1 && !local.length) {
      compareSearch.value = matches[0].address
      compareResults.innerHTML = ''
      await selectCompareParcel(matches[0].pin)
      return matches
    }
    compareStatus.textContent = local.length + matches.length > 1 ? SEARCH_COPY.pick : ''
    return matches
  } catch {
    if (local.length) {
      renderCompareChoices(local, [])
      compareStatus.textContent = ''
      return local
    }
    compareResults.innerHTML = ''
    compareStatus.textContent = SEARCH_COPY.error
    return []
  }
}

function finishComparePlace() {
  compareSearch.value = ''
  compareResults.innerHTML = ''
  compareStatus.textContent = ''
  paintCompare()
  compareSearch.focus()
}

function selectCompareChoice(choice) {
  cancelCompareSearch()
  if (choice.kind === 'county') {
    const item = countySubject(county)
    if (!item) return
    placeCompare(item)
  } else if (choice.kind === 'neighborhood') {
    const feature = tractGeojson?.features.find((row) => row.properties.id === choice.id)
    const item = neighborhoodSubject(feature?.properties || { id: choice.id, name: choice.label })
    if (!item) return
    placeCompare(item)
  }
  finishComparePlace()
}

async function selectCompareParcel(pin) {
  cancelCompareSearch()
  compareStatus.textContent = 'Loading…'
  try {
    const response = await fetch(`${API}/parcel?pin=${pin}`)
    if (!response.ok) throw new Error('parcel failed')
    const detail = await response.json()
    placeCompare(homeSubject(detail))
    finishComparePlace()
  } catch {
    compareStatus.textContent = SEARCH_COPY.error
  }
}

function neighborhoodGeometry(tractId) {
  if (!tractGeojson || !tractId) return null
  return tractGeojson.features.find((feature) => feature.properties.id === tractId)?.geometry || null
}

function openExportDocument(html, filename) {
  if (!html) return
  const popup = window.open('', '_blank')
  if (popup) {
    popup.document.write(html)
    popup.document.close()
    popup.focus()
    popup.print()
    return
  }
  const href = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  link.click()
  URL.revokeObjectURL(href)
}

function printOrDownloadSplit(home) {
  openExportDocument(
    exportSplitMarkup(home, county, {
      geometry: neighborhoodGeometry(home.tract?.id),
    }),
    exportFilename(home.address),
  )
}

function printOrDownloadCompare() {
  if (!compareA || !compareB) return
  openExportDocument(exportCompareMarkup(compareA, compareB, county), exportCompareFilename(compareA, compareB))
}

function goCountyView() {
  closeSale()
  closeDetails()
  closeCompare()
  applyWakeFrame(true)
}

document.querySelector('.brand').addEventListener('click', (event) => {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  goCountyView()
})
document.querySelector('#reset-map').addEventListener('click', goCountyView)

document.querySelector('#for-sale-toggle').addEventListener('click', () => {
  if (salePanelOpen()) closeSale()
  else openSale()
})
document.querySelector('#close-for-sale').addEventListener('click', () => closeSale())
document.querySelector('#sale-reset').addEventListener('click', () => {
  resetSaleControls()
  if (forSaleOn) paintListingLayer()
})
document.querySelector('#sale-show').addEventListener('click', () => {
  if (!listingRows.length) return
  setForSale(true)
  paintListingLayer()
})
for (const input of [salePriceMin, salePriceMax, saleLandMin, saleLandMax]) {
  input?.addEventListener('input', paintSaleCount)
}

document.querySelector('#compare-homes').addEventListener('click', () => {
  if (comparePanelOpen()) closeCompare()
  else openCompare()
})
document.querySelector('#close-compare').addEventListener('click', closeCompare)
document.querySelector('#compare-form').addEventListener('submit', (event) => {
  event.preventDefault()
  runCompareSearch(compareSearch.value, { submit: true })
})
compareSearch.addEventListener('input', () => {
  clearTimeout(compareTimer)
  compareTimer = setTimeout(() => runCompareSearch(compareSearch.value), 180)
})
compareResults.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-kind], button[data-pin]')
  if (!button) return
  const kind = button.dataset.kind || 'home'
  if (kind === 'home') {
    selectCompareParcel(button.dataset.pin)
    return
  }
  selectCompareChoice({
    kind,
    id: button.dataset.tractId,
    label: button.childNodes[0]?.textContent?.trim() || '',
  })
})
document.querySelector('#compare-body').addEventListener('click', (event) => {
  if (!event.target.closest('.compare-home.is-empty')) return
  compareSearch.focus()
})
exportButton.addEventListener('click', () => {
  if (canExportCompare()) printOrDownloadCompare()
  else if (selectedHome) printOrDownloadSplit(selectedHome)
})
document.addEventListener(
  'keydown',
  (event) => {
    if (event.key !== 'Escape') return
    if (salePanelOpen()) {
      event.preventDefault()
      event.stopImmediatePropagation()
      closeSale()
      return
    }
    if (!comparePanelOpen()) return
    event.preventDefault()
    event.stopImmediatePropagation()
    closeCompare()
  },
  true,
)

renderSuggestions()
initHint()
syncExport()
await Promise.all([loadCounty(), loadTracts(), loadListings()])
const walletReady = await fetch(`${API}/appeal`).then((response) => response.json())
if (walletReady.ready) saveButton.hidden = false
