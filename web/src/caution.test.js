import assert from 'node:assert/strict'
import test from 'node:test'

import { cautionFlags } from './caution.js'

const home = {
  land: 120000,
  building: 327000,
  land_share: 0.27,
  year_built: 1998,
  tract: { median_building: 327000 },
}

test('an ordinary house is not flagged', () => {
  assert.deepEqual(cautionFlags(home), [])
})

test('very high or low land share is flagged', () => {
  const high = cautionFlags({ ...home, land: 900000, building: 80000, land_share: 0.92 })
  assert.equal(high.some((flag) => flag.code === 'high-share'), true)
  const low = cautionFlags({ ...home, land: 20000, building: 400000, land_share: 0.05 })
  assert.equal(low.some((flag) => flag.code === 'low-share'), true)
})

test('a cheap building on expensive land is a teardown signal', () => {
  const flags = cautionFlags({ ...home, land: 400000, building: 50000, land_share: 0.89 })
  assert.equal(flags.some((flag) => flag.code === 'teardown-signal'), true)
})

test('an old house valued far below the tract is flagged', () => {
  const flags = cautionFlags({
    land: 120000,
    building: 80000,
    land_share: 0.6,
    year_built: 1960,
    tract: { median_building: 327000 },
  })
  assert.equal(flags.some((flag) => flag.code === 'old-vs-neighborhood'), true)
})

test('new construction is flagged', () => {
  const flags = cautionFlags({ ...home, year_built: new Date().getFullYear() })
  assert.equal(flags[0].code, 'new-construction')
})

test('missing values stop the split from looking precise', () => {
  const flags = cautionFlags({ land: 0, building: 100, land_share: 0 })
  assert.equal(flags[0].code, 'missing')
})
