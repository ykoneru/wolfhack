import assert from 'node:assert/strict'
import test from 'node:test'

import {
  NO_DATA_COLOR,
  barHeights,
  dollars,
  hotspotSentence,
  percentText,
  saleDateText,
  shareColor,
  shareRange,
  shareText,
  tractColor,
  tractLabel,
  verdictSentence,
} from './split.js'

test('tract colour follows how far land share sits from the county', () => {
  assert.equal(tractColor(-20), '#0369a1')
  assert.equal(tractColor(-8), '#38bdf8')
  assert.equal(tractColor(0), '#4a4a4a')
  assert.equal(tractColor(10), '#c9a227')
  assert.equal(tractColor(30), '#e8d48b')
})

test('a tract with too few homes is not coloured as if it were measured', () => {
  assert.equal(tractColor(null), NO_DATA_COLOR)
  assert.equal(tractLabel(null), 'Too few homes to grade')
  assert.equal(tractLabel(30), 'Mostly land')
})

test('numbers read the way a buyer expects', () => {
  assert.equal(dollars(351255), '$351,255')
  assert.equal(dollars(null), '—')
  assert.equal(shareText(0.312), '31%')
  assert.equal(percentText(10.5), '+10.5%')
  assert.equal(saleDateText('2024-05-12'), 'May 12, 2024')
})

test('the verdict sentence names house, lot, or teardown', () => {
  assert.match(verdictSentence({ verdict: 'house', land_share: 0.27 }), /mostly the house/)
  assert.match(verdictSentence({ verdict: 'lot', land_share: 0.45 }), /mostly land/)
  assert.match(
    verdictSentence({ verdict: 'teardown', land_share: 0.52, year_built: 1964 }),
    /Teardown watch/,
  )
})

test('hotspot copy uses the highest land-share tract', () => {
  const line = hotspotSentence({
    neighborhoods: [{ name: 'Census Tract 501', median_land_share: 0.41 }],
  })
  assert.match(line, /Census Tract 501/)
  assert.match(line, /41%/)
  assert.match(hotspotSentence({ neighborhoods: [] }), /No neighborhood/)
})

test('share colors follow the observed land-share range', () => {
  const range = shareRange([0.2, 0.4, 0.6])
  assert.deepEqual(range, { min: 0.2, max: 0.6 })
  assert.equal(shareColor(null, range), NO_DATA_COLOR)
  assert.equal(shareColor(0.2, range), '#0369a1')
  assert.equal(shareColor(0.6, range), '#e8d48b')
})

test('bars span the full chart without collapsing the shortest to nothing', () => {
  const bars = barHeights([
    { city: 'RALEIGH', median_land_share: 0.32 },
    { city: 'CARY', median_land_share: 0.28 },
    { city: 'ZEBULON', median_land_share: 0.18 },
  ])
  assert.equal(bars[0].height, 100)
  assert.equal(bars[2].height, 25)
})
