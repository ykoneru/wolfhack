import assert from 'node:assert/strict'
import test from 'node:test'

import {
  compareDelta,
  compareDeltaLine,
  compareMoneyDiffText,
  comparePointsDiffText,
  compareRates,
  compareShareMarks,
  compareSummary,
  compareViewHtml,
  countySubject,
  exportCompareFilename,
  exportCompareMarkup,
  exportFilename,
  exportSplitMarkup,
  isCountyCompareQuery,
  listingUpdatedLabel,
  matchNeighborhoods,
  neighborhoodOutlineSvg,
  neighborhoodSubject,
  splitSummary,
  typicalBandLabel,
  typicalCompareSentence,
} from './tools.js'

const home = {
  address: '1000 DOROTHEA DR',
  city: 'RALEIGH',
  verdict_label: 'Teardown watch',
  land_share: 0.75,
  land: 150000,
  building: 50000,
  assessed: 200000,
  year_built: 1935,
  tract: { name: 'Census Tract 510', median_land_share: 0.57 },
}

test('listing stamp says updated today without a new RentCast call', () => {
  const now = new Date('2026-10-04T12:00:00-04:00')
  assert.equal(listingUpdatedLabel('2026-10-04T05:40:00.755Z', now), 'updated today')
  assert.equal(listingUpdatedLabel('2026-10-01T05:40:00.755Z', now), 'updated Oct 1')
  assert.equal(listingUpdatedLabel(null, now), 'from cache')
})

test('export filenames are safe slugs', () => {
  assert.equal(exportFilename('1000 DOROTHEA DR'), 'parcel-1000-dorothea-dr.html')
  assert.equal(exportFilename(''), 'parcel-home.html')
  assert.equal(
    exportCompareFilename(home, { address: '100 POND BLUFF WAY' }),
    'parcel-compare-1000-dorothea-dr-100-pond-bluff-way.html',
  )
})

test('a split summary keeps the figures a homeowner would print', () => {
  const row = splitSummary(home, { median_land_share: 0.2567 })
  assert.equal(row.address, '1000 DOROTHEA DR')
  assert.equal(row.landShare, '75%')
  assert.equal(row.land, '$150,000')
  assert.equal(row.countyShare, '26%')
  assert.equal(row.tract, 'Census Tract 510')
})

test('compare delta is first minus second, in points not percents', () => {
  const later = { ...home, address: '200 OAK ST', land_share: 0.2, land: 80000, building: 320000, assessed: 400000 }
  const delta = compareDelta(home, later)
  assert.ok(Math.abs(delta.landShare - 0.55) < 0.0001)
  assert.equal(delta.land, 70000)
  assert.equal(delta.building, -270000)
  assert.equal(delta.assessed, -200000)
  assert.equal(compareDeltaLine(home, later), 'Land share is 55 points higher than 200 Oak St.')
  assert.equal(compareDeltaLine(home, home), 'Same land share.')
  assert.doesNotMatch(compareDeltaLine(home, later), /\d+% lower|\d+% higher/)
})

test('compare summary uses real dollar gaps and never invents a percentile', () => {
  const fishburn = {
    address: '209 FISHBURN DR',
    land: 200000,
    building: 600000,
    assessed: 800000,
    land_share: 0.25,
  }
  const other = {
    address: '100 MAIN ST',
    land: 105000,
    building: 443351,
    assessed: 548351,
    land_share: 0.19,
  }
  assert.equal(
    compareSummary(fishburn, other),
    '209 Fishburn Dr is assessed $251,649 higher, mostly from a $156,649 higher building value.',
  )
  assert.doesNotMatch(compareSummary(fishburn, other), /percentile/i)
})

test('a close building-value-per-sqft gap is described as mostly size', () => {
  const fishburn = {
    address: '209 FISHBURN DR',
    land: 210000,
    building: 667233,
    assessed: 877233,
    heated_area: 3303,
  }
  const toulouse = {
    address: '724 TOULOUSE CT',
    land: 115000,
    building: 510584,
    assessed: 625584,
    heated_area: 2592,
  }
  assert.match(compareSummary(fishburn, toulouse), /mostly size \(3,303 vs 2,592 sq ft\)/)
})

test('compare rates use heated area and hide land-per-acre without lot size', () => {
  const rates = compareRates({ building: 115077, heated_area: 1270, land: 345000 })
  assert.ok(Math.abs(rates.buildingPerSqft - 115077 / 1270) < 0.0001)
  assert.equal(rates.landPerAcre, undefined)
  assert.equal(rates.landPerSqft, undefined)
  assert.deepEqual(compareRates({ building: 115077, land: 345000 }), {})
})

test('compare differences use minus/plus and points for land share', () => {
  assert.equal(compareMoneyDiffText({ dollars: -95000, percent: -0.45 }), '−$95,000 (−45%)')
  assert.equal(comparePointsDiffText(-0.06), '−6 points')
  assert.equal(comparePointsDiffText(0.06), '+6 points')
})

test('the compare cards hide missing fields and keep caution wording', () => {
  const html = compareViewHtml(
    {
      kind: 'home',
      address: '1 MAIN ST',
      land_share: 0.91,
      land: 200000,
      building: 20000,
      assessed: 220000,
      listing: { price: 425000 },
    },
    { kind: 'home', address: '2 OAK ST', land_share: 0.2, land: 80000, building: 320000, assessed: 400000 },
    { median_land_share: 0.2567 },
  )
  assert.match(html, /1 Main St/)
  assert.match(html, /Difference vs 2 Oak St/)
  assert.match(html, /\+\$120,000/)
  assert.match(html, /Interpret with caution/)
  assert.match(html, /Land is more than 80% of the split/)
  assert.doesNotMatch(html, /undefined/)
  assert.doesNotMatch(html, /NaN/)
  assert.doesNotMatch(html, /HOUSE|House/)
  assert.doesNotMatch(html, /Land value \/ acre/)
  assert.doesNotMatch(html, /Lot size/)
  const slim = compareViewHtml({ kind: 'home', address: '2 MAIN ST', land_share: 0.2 }, null, {})
  assert.match(slim, /Add a second address/)
  assert.doesNotMatch(slim, /undefined/)
  assert.doesNotMatch(slim, /List /)
  const blank = compareViewHtml(null, null, {})
  assert.match(blank, /Add the first address/)
  assert.match(blank, /Add a second address/)
})

test('the second compare slot can be a neighborhood or the county typical', () => {
  assert.equal(isCountyCompareQuery('Wake County typical'), true)
  assert.equal(isCountyCompareQuery('toulouse'), false)
  const tract = neighborhoodSubject({
    id: '37183051000',
    name: 'Census Tract 510',
    median_land_share: 0.57,
    median_land: 414000,
    median_building: 250106,
    enough_homes: true,
  })
  const county = countySubject({ median_land_share: 0.2567, median_land: 120000, median_building: 327358 })
  const html = compareViewHtml(home, tract, { median_land_share: 0.2567 })
  assert.match(html, /points/)
  assert.doesNotMatch(html, /HOUSE/)
  assert.match(html, /Census Tract 510/)
  const marks = compareShareMarks(home, county, { median_land_share: 0.2567 })
  assert.ok(marks.some((mark) => mark.label === 'Wake County typical'))
  const hits = matchNeighborhoods(
    [{ properties: { id: '37183051000', name: 'Census Tract 510' } }],
    'tract 510',
  )
  assert.equal(hits[0].id, '37183051000')
})

test('the compare export includes both homes, the gap, and the assessed-not-market note', () => {
  const later = {
    address: '100 POND BLUFF WAY',
    city: 'CARY',
    verdict_label: 'Priced as a home',
    land_share: 0.2,
    land: 80000,
    building: 320000,
    assessed: 400000,
    year_built: 1998,
  }
  const html = exportCompareMarkup(home, later, { median_land_share: 0.2567 }, { now: new Date('2026-10-04T12:00:00-04:00') })
  assert.match(html, /1000 Dorothea Dr/)
  assert.match(html, /100 Pond Bluff Way/)
  assert.match(html, /What that means/)
  assert.match(html, /assessed values/)
  assert.match(html, /@page \{ size: Letter; margin: 0; \}/)
  assert.match(html, /October 4, 2026/)
  assert.doesNotMatch(html, /percentile/i)
  assert.equal(exportCompareMarkup(home, null, {}), '')
  assert.equal(exportCompareMarkup(null, later, {}), '')
})

test('the export page includes the address and the assessed-not-market note', () => {
  const html = exportSplitMarkup(home, { median_land_share: 0.2567 }, { now: new Date('2026-10-04T12:00:00-04:00') })
  assert.match(html, /1000 Dorothea Dr/)
  assert.match(html, /\$150,000/)
  assert.match(html, /assessed values/)
  assert.match(html, /@page \{ size: Letter; margin: 0; \}/)
  assert.match(html, /print-color-adjust: exact/)
  assert.match(html, /Wake County 2024 roll/)
  assert.match(html, /October 4, 2026/)
  assert.match(html, /More land than typical/)
  assert.match(html, /This home/)
  assert.match(html, /Neighborhood/)
  assert.match(html, /Wake County typical/)
  assert.doesNotMatch(html, /percentile/i)
  assert.doesNotMatch(html, /<svg class="tract-map"/)
  assert.doesNotMatch(html, /qr/i)
  assert.equal(exportSplitMarkup(null, {}), '')
})

test('typical-band labels use a 5-point window around the county share', () => {
  assert.equal(typicalBandLabel(0.18, 0.2567), 'More house than typical')
  assert.equal(typicalBandLabel(0.26, 0.2567), 'About typical')
  assert.equal(typicalBandLabel(0.40, 0.2567), 'More land than typical')
  assert.equal(typicalBandLabel(null, 0.2567), null)
  assert.doesNotMatch(typicalCompareSentence(0.18, 0.2567), /percentile/i)
})

test('missing export blocks stay off the page', () => {
  const html = exportSplitMarkup(
    { address: '1 MAIN ST', land_share: 0.2, land: 40000, building: 160000, assessed: 200000 },
    {},
  )
  assert.match(html, /1 Main St/)
  assert.doesNotMatch(html, /undefined/)
  assert.doesNotMatch(html, /NaN/)
  assert.doesNotMatch(html, /Built /)
  assert.doesNotMatch(html, /Neighborhood/)
  assert.doesNotMatch(html, /For sale/)
  assert.doesNotMatch(html, /Interpret with caution/)
  assert.doesNotMatch(html, /<svg class="tract-map"/)
})

test('caution wording and a matched listing appear only when present', () => {
  const html = exportSplitMarkup(
    {
      ...home,
      land: 200000,
      building: 20000,
      assessed: 220000,
      land_share: 0.91,
      listing: { price: 425000 },
    },
    { median_land_share: 0.2567 },
  )
  assert.match(html, /Interpret with caution/)
  assert.match(html, /Land is more than 80% of the split/)
  assert.match(html, /List \$425,000/)
  assert.match(html, /assessed \$220,000/)
  assert.match(html, /Assessments are not market prices/)
})

test('a neighborhood outline is an inline SVG, not a map tile', () => {
  const geometry = {
    type: 'Polygon',
    coordinates: [[
      [-78.7, 35.7],
      [-78.6, 35.7],
      [-78.6, 35.8],
      [-78.7, 35.8],
      [-78.7, 35.7],
    ]],
  }
  const svg = neighborhoodOutlineSvg(geometry, { lat: 35.75, lon: -78.65 })
  assert.match(svg, /<polygon /)
  assert.match(svg, /<circle /)
  assert.doesNotMatch(svg, /tile|openstreetmap|arcgis/i)
  assert.equal(neighborhoodOutlineSvg(null, { lat: 35.75, lon: -78.65 }), '')
  const html = exportSplitMarkup(home, { median_land_share: 0.2567 }, { geometry })
  assert.match(html, /tract-map/)
})
