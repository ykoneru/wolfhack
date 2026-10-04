// Reset / compare / export helpers. Kept separate so the summary math can be tested.

import { COMPARE, DISCLAIMER, EXPORT } from './config.js'
import { prettyPlace } from './conversation.js'
import { dollars, shareText } from './split.js'
import { cautionFlags } from './caution.js'

export function listingUpdatedLabel(iso, now = new Date()) {
  if (!iso) return 'from cache'
  const fetched = new Date(iso)
  if (Number.isNaN(fetched.getTime())) return 'from cache'
  if (fetched.toDateString() === now.toDateString()) return 'updated today'
  return `updated ${fetched.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
}

function slugPart(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

export function exportFilename(address) {
  return `parcel-${slugPart(address) || 'home'}.html`
}

export function exportCompareFilename(left, right) {
  const first = slugPart(compareSubjectName(left)) || 'first'
  const second = slugPart(compareSubjectName(right)) || 'second'
  return `parcel-compare-${first}-${second}.html`
}

export function reportDateText(now = new Date()) {
  return now.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}

export function typicalBandLabel(homeShare, countyShare, band = EXPORT.typicalBand) {
  if (!Number.isFinite(homeShare) || !Number.isFinite(countyShare)) return null
  const delta = homeShare - countyShare
  if (delta < -band) return EXPORT.moreHouse
  if (delta > band) return EXPORT.moreLand
  return EXPORT.aboutTypical
}

export function typicalCompareSentence(homeShare, countyShare, band = EXPORT.typicalBand) {
  const label = typicalBandLabel(homeShare, countyShare, band)
  if (!label) return ''
  return `Land is ${shareText(homeShare)} of this home’s assessed value. Wake County typical is ${shareText(countyShare)}. ${label}.`
}

export function splitSummary(home, county) {
  if (!home) return null
  return {
    address: home.address,
    city: home.city || '',
    verdict: home.verdict_label || home.verdict || '—',
    landShare: shareText(home.land_share),
    land: dollars(home.land),
    building: dollars(home.building),
    assessed: dollars(home.assessed),
    yearBuilt: home.year_built || '—',
    tract: home.tract?.name || '—',
    tractShare: shareText(home.tract?.median_land_share),
    countyShare: shareText(county?.median_land_share),
  }
}

function hasNumber(value) {
  return Number.isFinite(Number(value))
}

function moneyGap(left, right) {
  if (!hasNumber(left) || !hasNumber(right)) return null
  const dollarsDelta = Number(left) - Number(right)
  const base = Number(right)
  return {
    dollars: dollarsDelta,
    percent: base !== 0 ? dollarsDelta / base : null,
  }
}

export function compareSubjectName(item) {
  if (!item) return ''
  if (item.kind === 'county') return COMPARE.countyName
  if (item.kind === 'neighborhood') return item.label || item.tract?.name || item.address || ''
  return prettyPlace(item.address || item.label || '')
}

export function homeSubject(detail) {
  if (!detail) return null
  return { ...detail, kind: detail.kind || 'home', label: detail.address }
}

export function neighborhoodSubject(props) {
  if (!props?.name && !props?.id) return null
  return {
    kind: 'neighborhood',
    id: props.id,
    address: props.name,
    label: props.name,
    land: props.median_land,
    building: props.median_building,
    land_share: props.median_land_share,
    tract: {
      id: props.id,
      name: props.name,
      median_land_share: props.median_land_share,
      enough_homes: props.enough_homes,
    },
    verdict_label: 'Neighborhood typical',
  }
}

export function countySubject(stats) {
  if (!stats || !hasNumber(stats.median_land_share)) return null
  return {
    kind: 'county',
    id: 'wake',
    address: COMPARE.countyName,
    label: COMPARE.countyName,
    land: stats.median_land,
    building: stats.median_building,
    land_share: stats.median_land_share,
    verdict_label: 'County typical',
  }
}

export function isCountyCompareQuery(query) {
  const normalized = String(query || '')
    .toLowerCase()
    .replace(/[^a-z\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return COMPARE.countyQueries.includes(normalized)
}

export function matchNeighborhoods(features, query, limit = 6) {
  const needle = String(query || '').toLowerCase().replace(/\s+/g, ' ').trim()
  if (needle.length < 3 || !features?.length) return []
  const compact = needle.replace(/\s/g, '')
  return features
    .filter((feature) => {
      const name = String(feature.properties?.name || '').toLowerCase()
      const id = String(feature.properties?.id || '')
      return name.includes(needle) || id.includes(compact)
    })
    .slice(0, limit)
    .map((feature) => feature.properties)
}

export function compareDelta(left, right) {
  if (!left || !right) return null
  const land = moneyGap(left.land, right.land)
  const building = moneyGap(left.building, right.building)
  const assessed = moneyGap(left.assessed, right.assessed)
  const landShare =
    hasNumber(left.land_share) && hasNumber(right.land_share) ? left.land_share - right.land_share : null
  return {
    landShare,
    land: land?.dollars ?? null,
    building: building?.dollars ?? null,
    assessed: assessed?.dollars ?? null,
    landPercent: land?.percent ?? null,
    buildingPercent: building?.percent ?? null,
    assessedPercent: assessed?.percent ?? null,
  }
}

export function compareDeltaLine(left, right) {
  const delta = compareDelta(left, right)
  if (!delta || delta.landShare == null) return ''
  const points = Math.round(Math.abs(delta.landShare) * 100)
  if (points === 0) return COMPARE.sameShare
  const other = compareSubjectName(right)
  const dir = delta.landShare > 0 ? 'higher' : 'lower'
  return other ? `Land share is ${points} points ${dir} than ${other}.` : `Land share is ${points} points ${dir}.`
}

export function compareRates(item) {
  if (!item) return {}
  const rates = {}
  const building = Number(item.building)
  const heated = Number(item.heated_area)
  const land = Number(item.land)
  const acres = Number(item.acres ?? item.deeded_acres ?? item.lot_acres)
  const lotSqft = Number(item.lot_sqft ?? item.lot_size_sqft)
  if (hasNumber(building) && building > 0 && hasNumber(heated) && heated > 0) {
    rates.buildingPerSqft = building / heated
  }
  if (hasNumber(land) && land > 0 && hasNumber(acres) && acres > 0) {
    rates.landPerAcre = land / acres
  } else if (hasNumber(land) && land > 0 && hasNumber(lotSqft) && lotSqft > 0) {
    rates.landPerSqft = land / lotSqft
  }
  return rates
}

function signedMark(value) {
  if (!Number.isFinite(value) || value === 0) return ''
  return value > 0 ? '+' : '−'
}

export function compareMoneyDiffText(gap) {
  if (!gap || !Number.isFinite(gap.dollars)) return ''
  if (gap.dollars === 0) return '$0'
  const money = `${signedMark(gap.dollars)}${dollars(Math.abs(gap.dollars))}`
  if (gap.percent == null) return money
  return `${money} (${signedMark(gap.percent)}${Math.round(Math.abs(gap.percent) * 100)}%)`
}

export function comparePointsDiffText(delta) {
  if (!Number.isFinite(delta)) return ''
  const points = Math.round(Math.abs(delta) * 100)
  if (points === 0) return '0 points'
  return `${signedMark(delta)}${points} points`
}

export function compareCountDiffText(gap) {
  if (!gap || !Number.isFinite(gap.dollars)) return ''
  if (gap.dollars === 0) return '0'
  const amount = Math.round(Math.abs(gap.dollars)).toLocaleString('en-US')
  if (gap.percent == null) return `${signedMark(gap.dollars)}${amount}`
  return `${signedMark(gap.dollars)}${amount} (${signedMark(gap.percent)}${Math.round(Math.abs(gap.percent) * 100)}%)`
}

function areaText(value) {
  if (!hasNumber(value) || Number(value) <= 0) return ''
  return `${Math.round(Number(value)).toLocaleString('en-US')} sq ft`
}

export function compareSummary(left, right) {
  if (!left || !right) return ''
  const name = compareSubjectName(left)
  const other = compareSubjectName(right)
  if (!name) return ''
  const assessed = moneyGap(left.assessed, right.assessed)
  const leftRate = compareRates(left).buildingPerSqft
  const rightRate = compareRates(right).buildingPerSqft
  const closeRate =
    hasNumber(leftRate) &&
    hasNumber(rightRate) &&
    rightRate > 0 &&
    Math.abs(leftRate / rightRate - 1) < COMPARE.sizeGapBand
  const sizeNote =
    closeRate && areaText(left.heated_area) && areaText(right.heated_area)
      ? COMPARE.mostlySize(areaText(left.heated_area).replace(' sq ft', ''), areaText(right.heated_area).replace(' sq ft', ''))
      : ''
  if (assessed) {
    if (assessed.dollars === 0) return COMPARE.sameAssessed(name, other)
    const dir = assessed.dollars > 0 ? 'higher' : 'lower'
    if (sizeNote) return `${name} is assessed ${dollars(Math.abs(assessed.dollars))} ${dir}. ${sizeNote}`
    const land = moneyGap(left.land, right.land)
    const building = moneyGap(left.building, right.building)
    let mostly = ''
    if (land && building) {
      if (Math.abs(building.dollars) >= Math.abs(land.dollars) && building.dollars !== 0) {
        mostly = `, mostly from a ${dollars(Math.abs(building.dollars))} ${building.dollars > 0 ? 'higher' : 'lower'} building value`
      } else if (land.dollars !== 0) {
        mostly = `, mostly from a ${dollars(Math.abs(land.dollars))} ${land.dollars > 0 ? 'higher' : 'lower'} land value`
      }
    }
    return `${name} is assessed ${dollars(Math.abs(assessed.dollars))} ${dir}${mostly}.`
  }
  if (sizeNote) return sizeNote
  const share = hasNumber(left.land_share) && hasNumber(right.land_share) ? left.land_share - right.land_share : null
  if (share == null) return ''
  const points = Math.round(Math.abs(share) * 100)
  if (points === 0) return `${name} has the same land share as ${other}.`
  return `${name} has a land share ${points} points ${share > 0 ? 'higher' : 'lower'} than ${other}.`
}

function shareWidth(share) {
  return `${Math.round(Math.max(0, Math.min(1, share)) * 1000) / 10}%`
}

function callMeterHtml(item) {
  if (!hasNumber(item?.land_share)) return ''
  const state = item.verdict || ''
  return `<div class="meter" aria-hidden="true"><span class="compare-meter-fill" data-state="${escapeHtml(state)}" style="width:${shareWidth(item.land_share)}"></span></div>`
}

function homeMetaBits(item) {
  return [
    item.city ? prettyPlace(item.city) : '',
    item.year_built ? `${COMPARE.builtPrefix} ${item.year_built}` : '',
    areaText(item.heated_area),
  ].filter(Boolean)
}

function homeFiguresHtml(item) {
  const rates = compareRates(item || {})
  const pairs = [
    hasNumber(item?.land) ? [COMPARE.landLabel, dollars(item.land)] : null,
    hasNumber(item?.building) ? [COMPARE.buildingLabel, dollars(item.building)] : null,
    hasNumber(item?.assessed) ? [COMPARE.totalLabel, dollars(item.assessed)] : null,
    item?.kind === 'home' && hasNumber(item.price) ? ['Last sale', dollars(item.price)] : null,
    item?.kind !== 'home' && hasNumber(item?.land_share) ? [COMPARE.landShareLabel, shareText(item.land_share)] : null,
    item?.kind === 'home' && !hasNumber(item.price) && rates.buildingPerSqft
      ? [COMPARE.buildingPerSqft, dollars(rates.buildingPerSqft)]
      : null,
  ].filter(Boolean)
  if (!pairs.length) return ''
  return `<dl class="factors">${pairs
    .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`)
    .join('')}</dl>`
}

function emptySlotHtml(slot) {
  const second = slot === 'second'
  return `<section class="compare-home is-empty" data-slot="${second ? 'second' : 'first'}">
      <p class="eyebrow">${escapeHtml(second ? COMPARE.secondSlot : COMPARE.firstSlot)}</p>
      <p class="compare-empty-title">${escapeHtml(second ? COMPARE.addSecond : COMPARE.addFirst)}</p>
      <p class="muted">${escapeHtml(second ? COMPARE.emptySecond : COMPARE.empty)}</p>
    </section>`
}

function homeCardHtml(item, slot, county) {
  if (!item) return emptySlotHtml(slot)
  const name = compareSubjectName(item)
  const bits = homeMetaBits(item)
  const call = item.verdict_label || ''
  const countyShare = hasNumber(county?.median_land_share) ? shareText(county.median_land_share) : ''
  const caption = hasNumber(item.land_share)
    ? `Land is ${shareText(item.land_share)} of the split.${countyShare ? ` County typical is ${countyShare}.` : ''}`
    : ''
  return `<section class="compare-home" data-slot="${slot === 'second' ? 'second' : 'first'}">
      <p class="eyebrow">${escapeHtml(slot === 'second' ? COMPARE.secondSlot : COMPARE.firstSlot)}</p>
      <h1>${escapeHtml(name)}</h1>
      ${bits.length ? `<p class="muted compare-meta">${escapeHtml(bits.join(' · '))}</p>` : ''}
      ${
        call
          ? `<p class="eyebrow compare-call-label">${escapeHtml(COMPARE.theCall)}</p>
      <p class="score"${item.verdict ? ` data-state="${escapeHtml(item.verdict)}"` : ''}>${escapeHtml(call)}</p>`
          : ''
      }
      ${callMeterHtml(item)}
      ${caption ? `<p class="muted compare-caption">${escapeHtml(caption)}</p>` : ''}
      ${homeFiguresHtml(item)}
    </section>`
}

function compareMetricRows(left, right) {
  const leftRates = compareRates(left || {})
  const rightRates = compareRates(right || {})
  const both = Boolean(left && right)
  const rows = [
    {
      label: COMPARE.landLabel,
      left: hasNumber(left?.land) ? dollars(left.land) : '',
      right: hasNumber(right?.land) ? dollars(right.land) : '',
      diff: both ? compareMoneyDiffText(moneyGap(left.land, right.land)) : '',
    },
    {
      label: COMPARE.buildingLabel,
      left: hasNumber(left?.building) ? dollars(left.building) : '',
      right: hasNumber(right?.building) ? dollars(right.building) : '',
      diff: both ? compareMoneyDiffText(moneyGap(left.building, right.building)) : '',
    },
    {
      label: COMPARE.totalLabel,
      left: hasNumber(left?.assessed) ? dollars(left.assessed) : '',
      right: hasNumber(right?.assessed) ? dollars(right.assessed) : '',
      diff: both ? compareMoneyDiffText(moneyGap(left.assessed, right.assessed)) : '',
    },
    {
      label: COMPARE.buildingPerSqft,
      left: leftRates.buildingPerSqft ? dollars(leftRates.buildingPerSqft) : '',
      right: rightRates.buildingPerSqft ? dollars(rightRates.buildingPerSqft) : '',
      diff: both ? compareMoneyDiffText(moneyGap(leftRates.buildingPerSqft, rightRates.buildingPerSqft)) : '',
    },
    {
      label: COMPARE.heatedLabel,
      left: areaText(left?.heated_area),
      right: areaText(right?.heated_area),
      diff: both ? compareCountDiffText(moneyGap(left?.heated_area, right?.heated_area)) : '',
    },
    {
      label: COMPARE.lotLabel,
      left: areaText(left?.lot_sqft ?? left?.lot_size_sqft) || (hasNumber(left?.acres ?? left?.deeded_acres) ? `${left.acres ?? left.deeded_acres} acres` : ''),
      right: areaText(right?.lot_sqft ?? right?.lot_size_sqft) || (hasNumber(right?.acres ?? right?.deeded_acres) ? `${right.acres ?? right.deeded_acres} acres` : ''),
      diff: both ? compareCountDiffText(moneyGap(left?.lot_sqft ?? left?.lot_size_sqft, right?.lot_sqft ?? right?.lot_size_sqft)) : '',
    },
    {
      label: COMPARE.landShareLabel,
      left: hasNumber(left?.land_share) ? shareText(left.land_share) : '',
      right: hasNumber(right?.land_share) ? shareText(right.land_share) : '',
      diff: both ? comparePointsDiffText(left.land_share - right.land_share) : '',
    },
  ].filter((row) => row.left || row.right)
  return rows
}

export function compareShareMarks(left, right, county) {
  const marks = []
  const add = (key, label, share, color) => {
    if (!hasNumber(share)) return
    marks.push({ key, label, share: Number(share), color, left: shareWidth(share) })
  }
  if (left) {
    add('home-a', compareSubjectName(left) || 'First home', left.land_share, COMPARE.axisHomeA)
    if (left.kind !== 'neighborhood' && left.tract?.enough_homes !== false) {
      add('hood-a', left.tract?.name || 'Neighborhood', left.tract?.median_land_share, COMPARE.axisNeighborhood)
    }
  }
  if (right) {
    add('home-b', compareSubjectName(right) || 'Second home', right.land_share, COMPARE.axisHomeB)
    if (right.kind !== 'neighborhood' && right.tract?.enough_homes !== false) {
      add('hood-b', right.tract?.name || 'Neighborhood', right.tract?.median_land_share, COMPARE.axisNeighborhood)
    }
  }
  if (left?.kind !== 'county' && right?.kind !== 'county') {
    add('county', COMPARE.countyName, county?.median_land_share, COMPARE.axisCounty)
  }
  const seen = new Set()
  return marks.filter((mark) => {
    const id = `${mark.label}:${mark.share}`
    if (seen.has(id)) return false
    seen.add(id)
    return true
  })
}

function compareNotesHtml(items) {
  const flags = items.flatMap((item) => (item?.kind === 'home' ? cautionFlags(item).map((flag) => `${compareSubjectName(item)}: ${flag.reason}`) : []))
  const listings = items
    .filter((item) => item?.listing?.price && hasNumber(item.assessed))
    .map((item) => `${compareSubjectName(item)} is listed at ${dollars(item.listing.price)} against ${dollars(item.assessed)} assessed. ${COMPARE.listingNote}`)
  if (!flags.length && !listings.length) return ''
  return `<div class="compare-notes">
      ${flags.length ? `<p>${escapeHtml(COMPARE.cautionTitle)}. ${escapeHtml(flags.join(' '))}</p>` : ''}
      ${listings.map((line) => `<p>${escapeHtml(line)}</p>`).join('')}
    </div>`
}

export function compareViewHtml(left, right, county) {
  const cards = `<div class="compare-homes">
      ${homeCardHtml(left, 'first', county)}
      ${homeCardHtml(right, 'second', county)}
    </div>`
  if (!left || !right) return cards
  const meaning = compareSummary(left, right)
  const diffs = compareMetricRows(left, right).filter((row) => row.diff)
  const baseline = COMPARE.vs(compareSubjectName(right))
  return `${cards}
    <section class="compare-meaning">
      <p class="eyebrow">${escapeHtml(COMPARE.whatThatMeans)}</p>
      ${meaning ? `<div class="bits"><p>${escapeHtml(meaning)}</p></div>` : ''}
      <p class="eyebrow">${escapeHtml(baseline)}</p>
      ${
        diffs.length
          ? `<dl class="factors">${diffs
              .map((row) => `<div><dt>${escapeHtml(row.label)}</dt><dd>${escapeHtml(row.diff)}</dd></div>`)
              .join('')}</dl>`
          : ''
      }
    </section>
    ${compareNotesHtml([left, right])}`
}

function flattenRings(geometry) {
  if (!geometry) return []
  if (geometry.type === 'Polygon') return geometry.coordinates || []
  if (geometry.type === 'MultiPolygon') return (geometry.coordinates || []).flat()
  return []
}

export function neighborhoodOutlineSvg(geometry, home, size = 132) {
  const rings = flattenRings(geometry)
  if (!rings.length) return ''
  const points = rings.flat()
  if (!points.length) return ''
  const lons = points.map((pair) => pair[0])
  const lats = points.map((pair) => pair[1])
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const pad = 8
  const spanLon = maxLon - minLon || 1
  const spanLat = maxLat - minLat || 1
  const inner = size - pad * 2
  const scale = inner / Math.max(spanLon, spanLat)
  const project = (lon, lat) => {
    const x = pad + (lon - minLon) * scale
    const y = pad + (maxLat - lat) * scale
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }
  const paths = rings
    .map((ring) => ring.map(([lon, lat]) => project(lon, lat)).join(' '))
    .map((d) => `<polygon points="${d}" />`)
    .join('')
  let pin = ''
  if (hasNumber(home?.lat) && hasNumber(home?.lon)) {
    const [cx, cy] = project(home.lon, home.lat).split(',')
    pin = `<circle cx="${cx}" cy="${cy}" r="3.2" fill="${EXPORT.accent}" />`
  }
  return `<svg class="tract-map" viewBox="0 0 ${size} ${size}" aria-hidden="true">${paths}${pin}</svg>`
}

function parcelLogo() {
  return `<svg class="logo-mark" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z"/></svg>`
}

export function exportSplitMarkup(home, county, extras = {}) {
  if (!home?.address) return ''
  const now = extras.now || new Date()
  const generated = reportDateText(now)
  const countyShare = county?.median_land_share
  const tract = home.tract || {}
  const landShare = home.land_share
  const buildingShare = Number.isFinite(landShare) ? 1 - landShare : null
  const compare = typicalCompareSentence(landShare, countyShare)
  const band = typicalBandLabel(landShare, countyShare)
  const flags = cautionFlags(home)
  const listing = home.listing
  const geometry = extras.geometry || null
  const outline = neighborhoodOutlineSvg(geometry, home)

  const chips = [
    home.city ? `<span class="chip">${escapeHtml(prettyPlace(home.city))}</span>` : '',
    home.year_built ? `<span class="chip">Built ${escapeHtml(String(home.year_built))}</span>` : '',
  ].join('')

  const splitBar =
    Number.isFinite(landShare) && hasNumber(home.land) && hasNumber(home.building)
      ? `<section class="block">
          <p class="eyebrow">Assessed split</p>
          <div class="stack-bar" aria-hidden="true">
            <span class="seg building" style="width:${shareWidth(buildingShare)}"></span>
            <span class="seg land" style="width:${shareWidth(landShare)}"></span>
          </div>
          <div class="stack-labels">
            <span><i class="swatch building"></i> Building ${escapeHtml(dollars(home.building))} · ${escapeHtml(shareText(buildingShare))}</span>
            <span><i class="swatch land"></i> Land ${escapeHtml(dollars(home.land))} · ${escapeHtml(shareText(landShare))}</span>
          </div>
        </section>`
      : ''

  const compareRows = [
    ['This home', landShare],
    tract.enough_homes === false ? null : ['Neighborhood', tract.median_land_share],
    ['Wake County typical', countyShare],
  ]
    .filter((row) => row && Number.isFinite(row[1]))
    .map(
      ([label, share]) => `<div class="compare-row">
        <span>${escapeHtml(label)}</span>
        <span class="track"><span class="fill" style="width:${shareWidth(share)}"></span></span>
        <strong>${escapeHtml(shareText(share))}</strong>
      </div>`,
    )
    .join('')

  const facts = [
    hasNumber(home.land) ? ['Land', dollars(home.land)] : null,
    hasNumber(home.building) ? ['Building', dollars(home.building)] : null,
    hasNumber(home.assessed) ? ['Total assessed', dollars(home.assessed)] : null,
    home.year_built ? ['Year built', String(home.year_built)] : null,
    tract.name
      ? ['Neighborhood', tract.name, tract.id && tract.id !== tract.name ? tract.id : '']
      : null,
  ]
    .filter(Boolean)
    .map(
      ([label, value, note]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}${
        note ? `<small>${escapeHtml(note)}</small>` : ''
      }</dd></div>`,
    )
    .join('')

  const cautionBox = flags.length
    ? `<section class="caution">
        <p class="eyebrow">${escapeHtml(EXPORT.cautionTitle)}</p>
        ${flags.map((flag) => `<p>${escapeHtml(flag.reason)}</p>`).join('')}
      </section>`
    : ''

  const listingBox =
    listing?.price && hasNumber(home.assessed)
      ? `<section class="listing">
          <p class="eyebrow">For sale</p>
          <p>List ${escapeHtml(dollars(listing.price))} · assessed ${escapeHtml(dollars(home.assessed))}.</p>
          <p class="muted">${escapeHtml(EXPORT.listingNote)}</p>
        </section>`
      : ''

  const title = `Parcel · ${prettyPlace(home.address)}`
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>${escapeHtml(title)}</title>
    <style>
      @page { size: Letter; margin: 0; }
      html, body { width: 8.5in; height: 11in; margin: 0; }
      * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      body { font-family: "Inter", "Segoe UI", system-ui, sans-serif; color: ${EXPORT.ink}; background: ${EXPORT.paper}; }
      .page { width: 8.5in; height: 11in; display: flex; flex-direction: column; overflow: hidden; }
      .header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 36px; background: ${EXPORT.accent}; color: #fff; }
      .brand { display: flex; align-items: center; gap: 8px; font-weight: 750; letter-spacing: -0.04em; font-size: 22px; }
      .logo-mark { width: 22px; height: 22px; }
      .header-meta { text-align: right; font-size: 11px; line-height: 1.45; opacity: 0.95; }
      .body { flex: 1; padding: 22px 36px 12px; display: flex; flex-direction: column; gap: 16px; }
      h1 { margin: 0; font-size: 26px; letter-spacing: -0.02em; line-height: 1.15; }
      .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
      .chip { display: inline-block; padding: 3px 8px; border: 1px solid ${EXPORT.line}; border-radius: 999px; font-size: 11px; color: ${EXPORT.muted}; }
      .verdict { margin: 0; font-size: 20px; font-weight: 700; }
      .lede { margin: 4px 0 0; color: ${EXPORT.muted}; font-size: 13px; line-height: 1.45; }
      .eyebrow { margin: 0 0 6px; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: ${EXPORT.muted}; }
      .stack-bar { display: flex; height: 20px; border-radius: 6px; overflow: hidden; background: ${EXPORT.line}; }
      .seg.building { background: ${EXPORT.building}; }
      .seg.land { background: ${EXPORT.accent}; }
      .stack-labels, .compare-row, .facts { font-size: 12px; }
      .stack-labels { display: flex; justify-content: space-between; gap: 12px; margin-top: 6px; color: ${EXPORT.muted}; }
      .swatch { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; }
      .swatch.building { background: ${EXPORT.building}; }
      .swatch.land { background: ${EXPORT.accent}; }
      .compare-row { display: grid; grid-template-columns: 132px 1fr 42px; align-items: center; gap: 10px; margin-top: 6px; }
      .track { height: 8px; border-radius: 99px; background: ${EXPORT.line}; overflow: hidden; }
      .fill { display: block; height: 100%; background: ${EXPORT.accent}; }
      .compare-row strong { text-align: right; font-variant-numeric: tabular-nums; }
      .facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0; }
      .facts div { padding: 8px 10px; border: 1px solid ${EXPORT.line}; border-radius: 8px; }
      .facts dt { color: ${EXPORT.muted}; font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; }
      .facts dd { margin: 3px 0 0; font-size: 15px; font-weight: 650; }
      .facts small { display: block; margin-top: 2px; font-size: 10px; font-weight: 500; color: ${EXPORT.muted}; }
      .row { display: flex; gap: 16px; align-items: start; }
      .tract-map { width: 128px; height: 128px; flex: none; border: 1px solid ${EXPORT.line}; border-radius: 8px; background: #fffaf9; }
      .tract-map polygon { fill: #fff1f1; stroke: ${EXPORT.accent}; stroke-width: 1.4; }
      .caution, .listing { padding: 10px 12px; border-radius: 8px; }
      .caution { background: ${EXPORT.caution}; }
      .listing { border: 1px solid ${EXPORT.line}; }
      .caution p, .listing p { margin: 0 0 4px; font-size: 12px; line-height: 1.4; }
      .caution p:last-child, .listing p:last-child { margin-bottom: 0; }
      .muted { color: ${EXPORT.muted}; }
      .footer { padding: 10px 32px 14px; border-top: 1px solid ${EXPORT.line}; font-size: 9.5px; line-height: 1.45; color: ${EXPORT.muted}; }
      .footer p { margin: 0 0 3px; }
    </style>
  </head>
  <body>
    <article class="page">
      <header class="header">
        <div class="brand">${parcelLogo()}<span>Parcel<span class="brand-dot">.</span></span></div>
        <div class="header-meta">${escapeHtml(EXPORT.roll)}<br>${escapeHtml(generated)}</div>
      </header>
      <div class="body">
        <section>
          <h1>${escapeHtml(prettyPlace(home.address))}</h1>
          ${chips ? `<div class="chips">${chips}</div>` : ''}
        </section>
        ${
          home.verdict_label || compare
            ? `<section>
                ${home.verdict_label ? `<p class="verdict">${escapeHtml(home.verdict_label)}${band ? ` · ${escapeHtml(band)}` : ''}</p>` : ''}
                ${compare ? `<p class="lede">${escapeHtml(compare)}</p>` : ''}
              </section>`
            : ''
        }
        ${splitBar}
        ${
          compareRows
            ? `<section class="block"><p class="eyebrow">Land share</p>${compareRows}</section>`
            : ''
        }
        ${facts ? `<dl class="facts">${facts}</dl>` : ''}
        ${outline || cautionBox || listingBox ? `<div class="row">${outline}<div>${cautionBox}${listingBox}</div></div>` : ''}
      </div>
      <footer class="footer">
        <p>${escapeHtml(EXPORT.source)} Generated ${escapeHtml(generated)}.</p>
        <p>${escapeHtml(DISCLAIMER)}</p>
        <p>${escapeHtml(EXPORT.method)}</p>
      </footer>
    </article>
  </body>
</html>`
}

function exportCompareCard(item, slot, county) {
  const name = compareSubjectName(item)
  const bits = homeMetaBits(item)
  const call = item.verdict_label || ''
  const countyShare = hasNumber(county?.median_land_share) ? shareText(county.median_land_share) : ''
  const caption = hasNumber(item.land_share)
    ? `Land is ${shareText(item.land_share)} of the split.${countyShare ? ` County typical is ${countyShare}.` : ''}`
    : ''
  return `<section class="card">
      <p class="eyebrow">${escapeHtml(slot === 'second' ? COMPARE.secondSlot : COMPARE.firstSlot)}</p>
      <h2>${escapeHtml(name)}</h2>
      ${bits.length ? `<p class="lede">${escapeHtml(bits.join(' · '))}</p>` : ''}
      ${call ? `<p class="verdict">${escapeHtml(call)}</p>` : ''}
      ${caption ? `<p class="lede">${escapeHtml(caption)}</p>` : ''}
      ${homeFiguresHtml(item)}
    </section>`
}

export function exportCompareMarkup(left, right, county, extras = {}) {
  if (!left || !right) return ''
  const now = extras.now || new Date()
  const generated = reportDateText(now)
  const firstName = compareSubjectName(left)
  const secondName = compareSubjectName(right)
  const meaning = compareSummary(left, right)
  const diffs = compareMetricRows(left, right).filter((row) => row.diff)
  const notes = compareNotesHtml([left, right])
  const title = `Parcel · Compare ${firstName} and ${secondName}`
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>${escapeHtml(title)}</title>
    <style>
      @page { size: Letter; margin: 0; }
      html, body { width: 8.5in; height: 11in; margin: 0; }
      * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      body { font-family: "Inter", "Segoe UI", system-ui, sans-serif; color: ${EXPORT.ink}; background: ${EXPORT.paper}; }
      .page { width: 8.5in; height: 11in; display: flex; flex-direction: column; overflow: hidden; }
      .header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 36px; background: ${EXPORT.accent}; color: #fff; }
      .brand { display: flex; align-items: center; gap: 8px; font-weight: 750; letter-spacing: -0.04em; font-size: 22px; }
      .logo-mark { width: 22px; height: 22px; }
      .header-meta { text-align: right; font-size: 11px; line-height: 1.45; opacity: 0.95; }
      .body { flex: 1; padding: 22px 36px 12px; display: flex; flex-direction: column; gap: 16px; }
      h1 { margin: 0; font-size: 22px; letter-spacing: -0.02em; line-height: 1.15; }
      h2 { margin: 0; font-size: 16px; letter-spacing: -0.02em; line-height: 1.25; }
      .lede { margin: 4px 0 0; color: ${EXPORT.muted}; font-size: 12px; line-height: 1.45; }
      .verdict { margin: 8px 0 0; font-size: 16px; font-weight: 700; }
      .eyebrow { margin: 0 0 6px; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: ${EXPORT.muted}; }
      .homes { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
      .card { padding: 12px 14px; border: 1px solid ${EXPORT.line}; border-radius: 8px; }
      .factors { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0 0; }
      .factors div { padding: 8px 10px; border: 1px solid ${EXPORT.line}; border-radius: 8px; }
      .factors dt { color: ${EXPORT.muted}; font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; }
      .factors dd { margin: 3px 0 0; font-size: 14px; font-weight: 650; }
      .meaning p { margin: 0 0 8px; font-size: 13px; line-height: 1.45; }
      .muted { color: ${EXPORT.muted}; }
      .compare-notes { margin-top: 4px; }
      .compare-notes p { margin: 0 0 6px; font-size: 12px; line-height: 1.4; }
      .footer { padding: 10px 32px 14px; border-top: 1px solid ${EXPORT.line}; font-size: 9.5px; line-height: 1.45; color: ${EXPORT.muted}; }
      .footer p { margin: 0 0 3px; }
    </style>
  </head>
  <body>
    <article class="page">
      <header class="header">
        <div class="brand">${parcelLogo()}<span>Parcel<span class="brand-dot">.</span></span></div>
        <div class="header-meta">${escapeHtml(EXPORT.roll)}<br>${escapeHtml(generated)}</div>
      </header>
      <div class="body">
        <section>
          <p class="eyebrow">${escapeHtml(COMPARE.title)}</p>
          <h1>${escapeHtml(firstName)} and ${escapeHtml(secondName)}</h1>
        </section>
        <div class="homes">
          ${exportCompareCard(left, 'first', county)}
          ${exportCompareCard(right, 'second', county)}
        </div>
        ${
          meaning || diffs.length
            ? `<section class="meaning">
                <p class="eyebrow">${escapeHtml(COMPARE.whatThatMeans)}</p>
                ${meaning ? `<p>${escapeHtml(meaning)}</p>` : ''}
                <p class="eyebrow">${escapeHtml(COMPARE.vs(secondName))}</p>
                ${
                  diffs.length
                    ? `<dl class="factors">${diffs
                        .map((row) => `<div><dt>${escapeHtml(row.label)}</dt><dd>${escapeHtml(row.diff)}</dd></div>`)
                        .join('')}</dl>`
                    : ''
                }
              </section>`
            : ''
        }
        ${notes}
      </div>
      <footer class="footer">
        <p>${escapeHtml(EXPORT.source)} Generated ${escapeHtml(generated)}.</p>
        <p>${escapeHtml(DISCLAIMER)}</p>
        <p>${escapeHtml(EXPORT.method)}</p>
      </footer>
    </article>
  </body>
</html>`
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
