import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import './style.css'
import {
  afterAssistantSpoke,
  afterRecognitionEnded,
  normalizeQuestion,
  suggestedQuestions,
  toParagraphs,
  transcriptFromResults,
  trimHistory,
  voiceStatus,
} from './conversation.js'
import {
  NO_DATA_COLOR,
  SCALE,
  VERDICT_COLOR,
  barHeights,
  dollars,
  hotspotSentence,
  percentText,
  saleDateText,
  shareText,
  tractColor,
  tractLabel,
  verdictSentence,
} from './split.js'

const API = 'http://127.0.0.1:8000'
const WAKE_CENTER = [35.79, -78.65]

const map = L.map('map', { center: WAKE_CENTER, zoom: 10, zoomControl: true })
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap',
  maxZoom: 19,
}).addTo(map)

let county = null
let tractLayer = null
let salesLayer = null
let homeMarker = null
let selectedPin = null
let spoken = ''

function text(id, value) {
  document.querySelector(id).textContent = value
}

function show(id, visible) {
  document.querySelector(id).hidden = !visible
}

function frameMap(bounds) {
  const overlay = window.matchMedia('(min-width: 861px)').matches
  map.fitBounds(bounds, overlay
    ? { paddingTopLeft: [24, 24], paddingBottomRight: [408, 24] }
    : { padding: [24, 24] })
}

function renderLegend() {
  const items = SCALE.map(
    (step) => `<li><span class="swatch" style="background:${step.color}"></span> ${step.label}</li>`,
  )
  items.push(`<li><span class="swatch" style="background:${NO_DATA_COLOR}"></span> Too few homes</li>`)
  document.querySelector('#legend').innerHTML = items.join('')
}

function renderCounty() {
  const rows = [
    ['Typical land share', shareText(county.median_land_share)],
    ['Priced as a house', county.house_count.toLocaleString('en-US')],
    ['Priced as a lot', county.lot_count.toLocaleString('en-US')],
    ['Teardown watch', county.teardown_count.toLocaleString('en-US')],
  ]
  document.querySelector('#standards').innerHTML = rows
    .map(
      ([name, value]) => `<li>
        <span class="standard-name">${name}</span>
        <strong class="standard-value">${value}</strong>
      </li>`,
    )
    .join('')
  text('#verdict', `${shareText(county.median_land_share)} land`)
  document.querySelector('#verdict').dataset.state = 'house'
  text(
    '#verdict-note',
    `Measured on ${county.homes.toLocaleString('en-US')} single-family homes. Land share is land divided by land plus building. At 40% or more, the purchase is a lot.`,
  )
}

function renderCities(payload) {
  const top = (payload.cities || []).slice(0, 10)
  const bars = barHeights(top)
  document.querySelector('#bands').innerHTML = bars
    .map(
      (bar) => `<div class="bar" style="height:${bar.height}%"
        title="${bar.city} · ${shareText(bar.median_land_share)}">
        <span>${bar.city === top[0]?.city || bar.city === top[top.length - 1]?.city ? shareText(bar.median_land_share) : ''}</span>
      </div>`,
    )
    .join('')
  if (top.length >= 2) {
    text(
      '#tilt-headline',
      `${top[0].city} ${shareText(top[0].median_land_share)} · ${top[top.length - 1].city} ${shareText(top[top.length - 1].median_land_share)}`,
    )
  }
  text('#bands-source', 'Cities read left to right, highest land share to lowest. County land and building values only.')
}

function paintShareMeter(share) {
  const fill = document.querySelector('#ratio-fill')
  fill.style.width = `${Math.round(Math.max(0, Math.min(1, share)) * 100)}%`
  fill.dataset.state = share >= 0.4 ? 'heavy' : 'light'
}

function renderHome(detail) {
  selectedPin = detail.pin
  const built = detail.year_built ? `built ${detail.year_built}` : 'year built unknown'
  const area = detail.heated_area ? `${Math.round(detail.heated_area).toLocaleString('en-US')} sq ft` : 'size unknown'
  text('#home-address', detail.address)
  text('#home-meta', `${detail.city} · ${built} · ${area}`)

  text('#home-ratio', detail.verdict_label)
  document.querySelector('#home-ratio').dataset.state = detail.verdict
  paintShareMeter(detail.land_share)
  text(
    '#ratio-caption',
    `Land is ${shareText(detail.land_share)} of the split. County typical is ${shareText(county.median_land_share)}.`,
  )
  document.querySelector('#home-figures').innerHTML = [
    ['Land', dollars(detail.land)],
    ['Building', dollars(detail.building)],
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
  text('#chain-note', '')
  spoken = ''

  selectedAddress = detail.address
  history = []
  endTalk()
  renderChat()
  renderSuggestions()

  if (homeMarker) homeMarker.remove()
  homeMarker = L.circleMarker([detail.lat, detail.lon], {
    radius: 9,
    color: '#ffffff',
    weight: 2,
    fillColor: VERDICT_COLOR[detail.verdict] || '#ffffff',
    fillOpacity: 0.95,
  })
    .addTo(map)
    .bindPopup(`${detail.address}<br>${detail.verdict_label} · ${shareText(detail.land_share)} land`)
  map.setView([detail.lat, detail.lon], 14)
  loadTract(detail.tract.id)
}

function renderTract(detail) {
  text('#tract-name', detail.name)
  if (!detail.enough_homes) {
    text(
      '#tract-summary',
      `Only ${detail.homes} single-family homes here, under the 25 needed before a typical land share is worth reporting.`,
    )
    document.querySelector('#tract-figures').innerHTML = ''
  } else {
    text(
      '#tract-summary',
      `${tractLabel(detail.relative_to_county)} · ${detail.homes.toLocaleString('en-US')} homes · typical land share ${shareText(detail.median_land_share)}.`,
    )
    document.querySelector('#tract-figures').innerHTML = [
      ['Typical land share', shareText(detail.median_land_share)],
      ['Vs county', percentText(detail.relative_to_county)],
      ['Lots', detail.lot_count?.toLocaleString('en-US') ?? '—'],
      ['Teardown watch', detail.teardown_count?.toLocaleString('en-US') ?? '—'],
    ]
      .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
      .join('')
  }

  if (salesLayer) salesLayer.remove()
  salesLayer = L.layerGroup(
    detail.points.map((point) =>
      L.circleMarker([point.lat, point.lon], {
        radius: 4,
        weight: 1,
        color: VERDICT_COLOR[point.verdict] || '#8f8f8f',
        fillOpacity: 0.75,
      }).on('click', () => selectParcel(point.pin)),
    ),
  ).addTo(map)
}

async function loadTract(tractId) {
  const response = await fetch(`${API}/tract?id=${tractId}`)
  if (!response.ok) return
  renderTract(await response.json())
}

async function selectParcel(pin) {
  const response = await fetch(`${API}/parcel?pin=${pin}`)
  if (!response.ok) return
  renderHome(await response.json())
}

async function loadTracts() {
  const response = await fetch('/wake-tracts.geojson')
  const geojson = await response.json()
  tractLayer = L.geoJSON(geojson, {
    style: (feature) => ({
      color: '#030303',
      weight: 1,
      fillColor: tractColor(feature.properties.relative_to_county),
      fillOpacity: feature.properties.enough_homes ? 0.45 : 0.2,
    }),
    onEachFeature: (feature, layer) => {
      const props = feature.properties
      layer.bindTooltip(
        `${props.name}<br>${props.enough_homes ? `${shareText(props.median_land_share)} land · ${percentText(props.relative_to_county)}` : 'too few homes'}`,
        { sticky: true },
      )
      layer.on('click', () => loadTract(props.id))
    },
  }).addTo(map)
  frameMap(tractLayer.getBounds())
}

async function loadCounty() {
  county = await (await fetch(`${API}/county`)).json()
  renderCounty()
  text('#scope-headline', `Wake County · ${shareText(county.median_land_share)} land`)
  text(
    '#scope-detail',
    `${county.homes.toLocaleString('en-US')} single-family homes on the 2024 roll`,
  )
  renderCities(await (await fetch(`${API}/cities`)).json())
  await loadHotspots()
}

async function loadHotspots() {
  const response = await fetch(`${API}/hotspots`)
  if (!response.ok) return
  const payload = await response.json()
  text('#buy-headline', hotspotSentence(payload))
  text('#buy-note', payload.meaning)
  document.querySelector('#buy-places').innerHTML = payload.neighborhoods
    .map(
      (place) => `<button type="button" class="buy-place" data-tract="${place.id}">
        <strong>${place.name}</strong>
        <span>${place.homes} homes · ${place.teardown_count} teardown watch</span>
        <span class="buy-ratio">${shareText(place.median_land_share)} land · ${percentText(place.relative_to_county)}</span>
      </button>`,
    )
    .join('')
}

document.querySelector('#buy-places').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-tract]')
  if (button) loadTract(button.dataset.tract)
})

const searchInput = document.querySelector('#search')
const searchResults = document.querySelector('#search-results')
let searchTimer = null

function renderMatches(matches) {
  searchResults.innerHTML = matches
    .map(
      (match) => `<button type="button" data-pin="${match.pin}" data-address="${match.address}">
        ${match.address}<span class="match-city">${match.city}${match.verdict ? ` · ${match.verdict}` : ''}</span>
      </button>`,
    )
    .join('')
}

async function runSearch(query) {
  if (query.trim().length < 3) {
    searchResults.innerHTML = ''
    return
  }
  const response = await fetch(`${API}/search?q=${encodeURIComponent(query)}`)
  if (!response.ok) return
  renderMatches((await response.json()).matches)
}

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => runSearch(searchInput.value), 180)
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
    await runSearch(button.dataset.query)
    const first = searchResults.querySelector('button[data-pin]')
    if (first) first.click()
  })
})

const hear = document.querySelector('#hear')
hear.addEventListener('click', async () => {
  if (!selectedPin) return
  hear.disabled = true
  const original = hear.textContent
  try {
    if (!spoken) {
      hear.textContent = 'Thinking…'
      const response = await fetch(`${API}/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin: selectedPin }),
      })
      const payload = await response.json()
      spoken = payload.reply
      document.querySelector('#gap-bits').innerHTML = spoken
        .split(/(?<=\.)\s+/)
        .filter(Boolean)
        .map((line) => `<p>${line}</p>`)
        .join('')
    }
    hear.textContent = 'Speaking…'
    await speak(spoken)
  } finally {
    hear.textContent = original
    hear.disabled = false
  }
})

const chat = document.querySelector('#chat')
const suggestions = document.querySelector('#suggestions')
const askForm = document.querySelector('#ask-form')
const questionInput = document.querySelector('#question')
const askButton = document.querySelector('#ask')
const talkButton = document.querySelector('#talk')
const stopTalk = document.querySelector('#stop-talk')
const voiceLine = document.querySelector('#voice-status')
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
let history = []
let selectedAddress = null
let player = null
let speakDone = null
let recognition = null
let talking = false
let voiceState = 'idle'
let lastHeard = ''

function setVoiceState(state) {
  voiceState = state
  voiceLine.textContent = voiceStatus(state)
  voiceLine.dataset.state = state
  talkButton.hidden = talking
  stopTalk.hidden = !talking
}

function renderChat(pending, listening) {
  const turns = history.map(
    (turn) => `<div class="turn turn-${turn.role}">
      <span class="who">${turn.role === 'you' ? 'You' : 'House or Lot'}</span>
      ${toParagraphs(turn.text).map((line) => `<p>${line}</p>`).join('')}
    </div>`,
  )
  if (listening) {
    turns.push(`<div class="turn turn-you pending"><span class="who">You</span><p>${listening}</p></div>`)
  }
  if (pending) {
    turns.push(`<div class="turn turn-assistant pending"><span class="who">House or Lot</span><p>${pending}</p></div>`)
  }
  chat.innerHTML = turns.join('')
  chat.scrollTop = chat.scrollHeight
}

function renderSuggestions() {
  suggestions.innerHTML = suggestedQuestions(selectedAddress ? { address: selectedAddress } : null)
    .map((question) => `<button type="button" class="suggestion">${question}</button>`)
    .join('')
}

function stopVoice() {
  if (player) {
    player.pause()
    player = null
  }
  if (speakDone) {
    speakDone()
    speakDone = null
  }
}

function stopRecognition() {
  if (!recognition) return
  recognition.onresult = null
  recognition.onerror = null
  recognition.onend = null
  try {
    recognition.stop()
  } catch {
    // Already stopped.
  }
  recognition = null
}

function endTalk() {
  talking = false
  lastHeard = ''
  stopRecognition()
  stopVoice()
  setVoiceState('idle')
}

async function speak(text) {
  const response = await fetch(`${API}/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) return
  stopVoice()
  player = new Audio(URL.createObjectURL(await response.blob()))
  await player.play()
  await new Promise((resolve) => {
    speakDone = resolve
    player.addEventListener('ended', resolve, { once: true })
    player.addEventListener('error', resolve, { once: true })
  })
  speakDone = null
  player = null
}

function startListening() {
  if (!talking) return
  if (!SpeechRecognition) {
    talking = false
    setVoiceState('idle')
    voiceLine.textContent = 'This browser cannot listen. Type a question instead.'
    return
  }
  stopRecognition()
  lastHeard = ''
  recognition = new SpeechRecognition()
  recognition.lang = 'en-US'
  recognition.continuous = false
  recognition.interimResults = true
  recognition.maxAlternatives = 1
  recognition.onresult = (event) => {
    const heard = transcriptFromResults(event.results)
    lastHeard = heard.final || heard.heard
    if (heard.heard) renderChat(null, heard.heard)
  }
  recognition.onerror = (event) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      talking = false
      setVoiceState('idle')
      voiceLine.textContent = 'Allow the microphone, then click Talk again.'
    }
  }
  recognition.onend = async () => {
    const heard = lastHeard
    lastHeard = ''
    const next = afterRecognitionEnded(talking, heard)
    setVoiceState(next)
    if (next === 'thinking') {
      await sendQuestion(heard)
    } else if (next === 'listening') {
      window.setTimeout(() => {
        if (talking && voiceState === 'listening') startListening()
      }, 250)
    }
  }
  setVoiceState('listening')
  try {
    recognition.start()
  } catch {
    // A second start while the last one is closing.
  }
}

async function sendQuestion(raw) {
  const question = normalizeQuestion(raw)
  if (!question) return
  questionInput.value = ''
  askButton.disabled = true
  history.push({ role: 'you', text: question })
  setVoiceState(talking ? 'thinking' : voiceState)
  renderChat('Thinking…')
  try {
    const response = await fetch(`${API}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pin: selectedPin || '',
        question,
        history: trimHistory(history.slice(0, -1)),
      }),
    })
    const payload = await response.json()
    const reply = payload.reply || payload.error || 'That did not go through. Try again.'
    history.push({ role: 'assistant', text: reply })
    renderChat()
    if (talking) setVoiceState('speaking')
    await speak(reply)
  } catch (error) {
    history.push({ role: 'assistant', text: 'The assistant is unreachable. Check that the API is running.' })
    renderChat()
  } finally {
    askButton.disabled = false
    if (!talking) questionInput.focus()
    else if (afterAssistantSpoke(talking) === 'listening') startListening()
  }
}

talkButton.addEventListener('click', () => {
  talking = true
  setVoiceState('listening')
  startListening()
})

stopTalk.addEventListener('click', endTalk)

askForm.addEventListener('submit', (event) => {
  event.preventDefault()
  sendQuestion(questionInput.value)
})

suggestions.addEventListener('click', (event) => {
  const button = event.target.closest('.suggestion')
  if (button) sendQuestion(button.textContent)
})

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

renderLegend()
renderSuggestions()
await Promise.all([loadCounty(), loadTracts()])
const walletReady = await fetch(`${API}/appeal`).then((response) => response.json())
if (walletReady.ready) saveButton.hidden = false
