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
  barHeights,
  dollars,
  gapSentence,
  inheritSentence,
  percentText,
  ratioText,
  saleDateText,
  standardRow,
  tiltSummary,
  tractColor,
  tractLabel,
} from './fairness.js'

const API = 'http://127.0.0.1:8000'
const WAKE_CENTER = [35.79, -78.65]

const map = L.map('map', { center: WAKE_CENTER, zoom: 10, zoomControl: true })
// Standard OSM tiles, darkened in CSS so the basemap sits behind the data
// instead of competing with it.
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
  items.push(`<li><span class="swatch" style="background:${NO_DATA_COLOR}"></span> Too few sales</li>`)
  document.querySelector('#legend').innerHTML = items.join('')
}

function renderStandards() {
  const limits = county.standards
  const rows = [
    standardRow('Median ratio', county.median_ratio, limits.median_ratio, ratioText),
    standardRow('Uniformity (COD)', county.cod, [0, limits.cod_max], (value) => value.toFixed(1)),
    standardRow('Price-related differential', county.prd, limits.prd, ratioText),
    standardRow('Price-related bias', county.prb, limits.prb, (value) => value.toFixed(3)),
  ]
  document.querySelector('#standards').innerHTML = rows
    .map(
      (row) => `<li class="${row.passes ? 'passes' : 'fails'}">
        <span class="standard-name">${row.name}</span>
        <strong class="standard-value">${row.value}</strong>
        <span class="standard-range">standard ${row.range}</span>
        <span class="standard-mark">${row.passes ? 'meets' : 'misses'}</span>
      </li>`,
    )
    .join('')

  const passes = rows.filter((row) => row.passes).length
  text('#verdict', passes === rows.length ? 'Meets all four' : `Misses ${rows.length - passes} of four`)
  document.querySelector('#verdict').dataset.state = passes === rows.length ? 'pass' : 'fail'
  text(
    '#verdict-note',
    `Measured on ${county.sales.toLocaleString('en-US')} arm's-length single-family sales from ${county.basis_year}, the year the current assessments took effect. Thresholds are the IAAO Standard on Ratio Studies.`,
  )
}

function renderBands(payload) {
  const bars = barHeights(payload.bands)
  document.querySelector('#bands').innerHTML = bars
    .map(
      (bar) => `<div class="bar" style="height:${bar.height}%" data-band="${bar.band}"
        title="${dollars(bar.low_price)} to ${dollars(bar.high_price)} · ratio ${ratioText(bar.median_ratio)}">
        <span>${bar.band === 1 || bar.band === bars.length ? ratioText(bar.median_ratio) : ''}</span>
      </div>`,
    )
    .join('')
  const tilt = tiltSummary(payload.bands)
  text(
    '#tilt-headline',
    tilt.regressive
      ? `${tilt.spread} points lower on the priciest homes`
      : `${Math.abs(tilt.spread)} points higher on the priciest homes`,
  )
  text(
    '#bands-source',
    `Cheapest tenth of homes sit at ${ratioText(tilt.cheapest)}, the priciest tenth at ${ratioText(tilt.priciest)}. Bands read left to right, cheapest to most expensive. Stored in ${payload.source === 'tiger' ? 'Tiger Data' : 'fairness.json'}.`,
  )
}

function paintRatioMeter(ratio) {
  // Centre the rail on the county median so the fill reads as a deviation.
  // The span covers the trimmed range of real ratios without clamping them.
  const span = 0.6
  const share = Math.max(0, Math.min(1, (ratio - (county.median_ratio - span / 2)) / span))
  const fill = document.querySelector('#ratio-fill')
  fill.style.width = `${Math.round(share * 100)}%`
  fill.dataset.state = ratio > county.median_ratio ? 'heavy' : 'light'
}

function renderHome(detail) {
  selectedPin = detail.pin
  text('#home-address', detail.address)
  text(
    '#home-meta',
    `${detail.city} · sold ${saleDateText(detail.sale_date)} · built ${detail.year_built || '—'} · ${Math.round(detail.heated_area).toLocaleString('en-US')} sq ft`,
  )

  text('#home-ratio', ratioText(detail.ratio))
  paintRatioMeter(detail.ratio)
  text(
    '#ratio-caption',
    `County median is ${ratioText(county.median_ratio)}. This home sits ${percentText(100 * (detail.ratio / county.median_ratio - 1))} from it.`,
  )
  document.querySelector('#home-figures').innerHTML = [
    ['Sold for', dollars(detail.price)],
    ['Assessed at', dollars(detail.assessed)],
    ['County norm', dollars(detail.versus_county.implied_assessed)],
    ['Difference', dollars(detail.versus_county.difference)],
  ]
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
    .join('')
  show('#ratio-card', true)

  const bits = []
  if (detail.same_moment) {
    bits.push(gapSentence(detail.versus_county))
    if (detail.band) {
      bits.push(
        `Homes in this price band, ${dollars(detail.band.low_price)} to ${dollars(detail.band.high_price)}, carry a median ratio of ${ratioText(detail.band.median_ratio)} across ${detail.band.sales.toLocaleString('en-US')} sales.`,
      )
    }
    if (detail.band && detail.cheapest_band_ratio > detail.band.median_ratio) {
      bits.push(
        `The cheapest tenth of Wake homes carry ${ratioText(detail.cheapest_band_ratio)}. At that ratio this home would be assessed ${dollars(detail.tilt.implied_assessed)}.`,
      )
    }
  } else {
    bits.push(
      `This house last sold in ${detail.sale_year || 'another year'} for ${dollars(detail.price)}. The assessment, ${dollars(detail.assessed)}, is from the 2024 roll, so the ratio is not the same test as a 2024 sale.`,
    )
    if (detail.tract.median_ratio) {
      bits.push(
        `2024 sales in ${detail.tract.name} sit at a median ratio of ${ratioText(detail.tract.median_ratio)}. That is the fair comparison for this neighborhood.`,
      )
    }
  }
  bits.push(
    `A buyer of this house inherits the ${dollars(detail.assessed)} assessment until the 2028 revaluation. The sale price does not reset what the county taxes.`,
  )
  document.querySelector('#gap-bits').innerHTML = bits.map((line) => `<p>${line}</p>`).join('')
  show('#gap-card', true)
  text('#chain-note', '')
  spoken = ''

  // A new home is a new conversation, so earlier answers cannot be mistaken
  // for answers about this one.
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
    fillColor: '#ffffff',
    fillOpacity: 0.9,
  })
    .addTo(map)
    .bindPopup(`${detail.address}<br>ratio ${ratioText(detail.ratio)}`)
  map.setView([detail.lat, detail.lon], 14)
  loadTract(detail.tract.id)
}

function renderTract(detail) {
  text('#tract-name', detail.name)
  if (!detail.enough_sales) {
    text(
      '#tract-summary',
      `Only ${detail.sales} qualifying ${county.basis_year} sales here, under the 15 needed before a median is worth reporting.`,
    )
    document.querySelector('#tract-figures').innerHTML = ''
  } else {
    text(
      '#tract-summary',
      `${tractLabel(detail.relative_to_county)} · ${detail.sales.toLocaleString('en-US')} sales measured · median home sold for ${dollars(detail.median_price)}.`,
    )
    const housing = detail.housing || {}
    document.querySelector('#tract-figures').innerHTML = [
      ['Median ratio', ratioText(detail.median_ratio)],
      ['Vs county', percentText(detail.relative_to_county)],
      ['Spread (COD)', detail.cod.toFixed(1)],
      ['Owner occupied', housing.owner_share === null || housing.owner_share === undefined
        ? '—'
        : `${Math.round(housing.owner_share * 100)}%`],
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
        color: point.ratio > detail.county_median_ratio ? '#e5484d' : '#10b981',
        fillOpacity: 0.7,
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
      fillOpacity: feature.properties.enough_sales ? 0.45 : 0.2,
    }),
    onEachFeature: (feature, layer) => {
      const props = feature.properties
      layer.bindTooltip(
        `${props.name}<br>${props.enough_sales ? `ratio ${ratioText(props.median_ratio)} · ${percentText(props.relative_to_county)}` : 'too few sales'}`,
        { sticky: true },
      )
      layer.on('click', () => loadTract(props.id))
    },
  }).addTo(map)
  frameMap(tractLayer.getBounds())
}

async function loadCounty() {
  county = await (await fetch(`${API}/county`)).json()
  renderStandards()
  text('#scope-headline', `Wake County · median ratio ${ratioText(county.median_ratio)}`)
  text(
    '#scope-detail',
    `${county.sales.toLocaleString('en-US')} single-family sales from ${county.basis_year}, the year the current values took effect`,
  )
  renderBands(await (await fetch(`${API}/bands`)).json())
  await loadInherit(350000)
}

async function loadInherit(budget) {
  const response = await fetch(`${API}/inherit?budget=${budget}`)
  if (!response.ok) return
  const payload = await response.json()
  text('#buy-headline', inheritSentence(payload))
  document.querySelector('#budget').value = String(Math.round(payload.budget))
  if (!payload.sales) {
    text('#buy-note', 'No 2024 sales closed at or under that budget.')
    document.querySelector('#buy-places').innerHTML = ''
    return
  }
  text(
    '#buy-note',
    `${payload.sales.toLocaleString('en-US')} sales at or under ${dollars(payload.budget)}. ` +
      `Neighborhoods below are where those buyers inherited the heaviest ratios. Assessments stay until ${payload.next_revaluation}.`,
  )
  document.querySelector('#buy-places').innerHTML = payload.neighborhoods
    .map(
      (place) => `<button type="button" class="buy-place" data-tract="${place.id}">
        <strong>${place.name}</strong>
        <span>${place.sales} sales · typical ${dollars(place.median_price)}</span>
        <span class="buy-ratio">${ratioText(place.median_ratio)} · ${percentText(place.relative_to_county)}</span>
      </button>`,
    )
    .join('')
}

document.querySelector('#buy-form').addEventListener('submit', (event) => {
  event.preventDefault()
  loadInherit(Number(document.querySelector('#budget').value))
})

document.querySelector('#buy-presets').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-budget]')
  if (!button) return
  loadInherit(Number(button.dataset.budget))
})

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
        ${match.address}<span class="match-city">${match.city} · ${saleDateText(match.sale_date)}</span>
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
      <span class="who">${turn.role === 'you' ? 'You' : 'Fair Share'}</span>
      ${toParagraphs(turn.text).map((line) => `<p>${line}</p>`).join('')}
    </div>`,
  )
  if (listening) {
    turns.push(`<div class="turn turn-you pending"><span class="who">You</span><p>${listening}</p></div>`)
  }
  if (pending) {
    turns.push(`<div class="turn turn-assistant pending"><span class="who">Fair Share</span><p>${pending}</p></div>`)
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
