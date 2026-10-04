import assert from 'node:assert/strict'
import test from 'node:test'

import {
  NO_DATA_COLOR,
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
  withinStandard,
} from './fairness.js'

test('tract colour follows how far the tract sits from the county', () => {
  assert.equal(tractColor(-9), '#0f766e')
  assert.equal(tractColor(-2), '#10b981')
  assert.equal(tractColor(0), '#4a4a4a')
  assert.equal(tractColor(2), '#e5484d')
  assert.equal(tractColor(9), '#a2191f')
})

test('a tract with too few sales is not coloured as if it were measured', () => {
  assert.equal(tractColor(null), NO_DATA_COLOR)
  assert.equal(tractColor(undefined), NO_DATA_COLOR)
  assert.equal(tractLabel(null), 'Too few sales to grade')
  assert.equal(tractLabel(5), 'Assessed much heavier')
})

test('numbers read the way a homeowner expects', () => {
  assert.equal(dollars(351255), '$351,255')
  assert.equal(dollars(-351255), '-$351,255')
  assert.equal(dollars(0), '$0')
  assert.equal(dollars(null), '—')
  assert.equal(ratioText(0.9506), '0.951')
  assert.equal(percentText(10.5), '+10.5%')
  assert.equal(percentText(-25.5), '-25.5%')
  assert.equal(saleDateText('2024-05-12'), 'May 12, 2024')
  assert.equal(saleDateText(null), '—')
})

test('a measure passes only inside the published range', () => {
  assert.ok(withinStandard(1.0161, [0.98, 1.03]))
  assert.ok(!withinStandard(1.04, [0.98, 1.03]))
  assert.ok(withinStandard(0.98, [0.98, 1.03]), 'the bound itself passes')

  const row = standardRow('PRD', 1.0161, [0.98, 1.03], ratioText)
  assert.equal(row.value, '1.016')
  assert.equal(row.range, '0.980–1.030')
  assert.ok(row.passes)
})

test('the gap sentence names the direction', () => {
  assert.match(
    gapSentence({ difference: 40000, percent: 10.5 }),
    /\$40,000 above the county norm, \+10\.5%/,
  )
  assert.match(gapSentence({ difference: -351255, percent: -25.5 }), /below the county norm/)
  assert.equal(
    gapSentence({ difference: 0, percent: 0 }),
    'This assessment sits exactly at the county norm.',
  )
})

test('the price band tilt reports the spread cheapest to priciest', () => {
  const bands = [
    { band: 1, median_ratio: 0.982 },
    { band: 2, median_ratio: 0.95 },
    { band: 3, median_ratio: 0.9075 },
  ]
  const tilt = tiltSummary(bands)
  assert.equal(tilt.cheapest, 0.982)
  assert.equal(tilt.priciest, 0.9075)
  assert.equal(tilt.spread, 7.5)
  assert.ok(tilt.regressive)

  const flat = tiltSummary([{ median_ratio: 0.95 }, { median_ratio: 0.95 }])
  assert.equal(flat.spread, 0)
  assert.ok(!flat.regressive)
  assert.equal(tiltSummary([]), null)
})

test('bars span the full chart without collapsing the shortest to nothing', () => {
  const bars = barHeights([
    { band: 1, median_ratio: 0.982 },
    { band: 2, median_ratio: 0.95 },
    { band: 3, median_ratio: 0.9075 },
  ])
  assert.equal(bars[0].height, 100)
  assert.equal(bars[2].height, 25)
  assert.ok(bars[1].height > 25 && bars[1].height < 100)

  const equal = barHeights([{ median_ratio: 0.95 }, { median_ratio: 0.95 }])
  assert.deepEqual(equal.map((bar) => bar.height), [25, 25])
})

test('a buyer inherits the assessment until the next revaluation', () => {
  const line = inheritSentence({
    budget: 350000,
    median_ratio: 0.968,
    county_median_ratio: 0.951,
    heavier_than_county: true,
    next_revaluation: 2028,
  })
  assert.match(line, /\$350,000/)
  assert.match(line, /0\.968/)
  assert.match(line, /heavier/)
  assert.match(line, /2028/)
  assert.match(inheritSentence({ budget: 10000, median_ratio: null }), /No 2024 sales/)
})
