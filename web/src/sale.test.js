import assert from 'node:assert/strict'
import test from 'node:test'

import {
  defaultSalePrefs,
  landFilterIsOpen,
  parseSaleNumber,
  passesSaleFilters,
  saleCountLabel,
  saleMatches,
} from './sale.js'

const cheap = { address: '1 A ST', price: 250000, land_share: 0.2 }
const mid = { address: '2 B ST', price: 600000, land_share: 0.45 }
const landHeavy = { address: '3 C ST', price: 900000, land_share: 0.7 }
const unknownShare = { address: '4 D ST', price: 400000 }
const noPrice = { address: '5 E ST', land_share: 0.3 }

test('empty sale fields leave every cached listing in', () => {
  const open = defaultSalePrefs()
  assert.equal(landFilterIsOpen(open), true)
  assert.equal(passesSaleFilters(cheap, open), true)
  assert.equal(passesSaleFilters(unknownShare, open), true)
  assert.equal(passesSaleFilters(noPrice, open), true)
  assert.equal(saleMatches([cheap, mid, unknownShare], open).length, 3)
})

test('price numbers keep the listings inside that list-price band', () => {
  const prefs = { ...defaultSalePrefs(), priceMin: 300000, priceMax: 800000 }
  assert.deepEqual(
    saleMatches([cheap, mid, landHeavy, noPrice], prefs).map((row) => row.address),
    ['2 B ST'],
  )
})

test('a 0–100 land range still keeps listings that have no county split', () => {
  const prefs = { ...defaultSalePrefs(), landMin: 0, landMax: 100 }
  assert.equal(landFilterIsOpen(prefs), true)
  assert.equal(passesSaleFilters(unknownShare, prefs), true)
})

test('a narrowed land range keeps only listings with a known split in band', () => {
  const prefs = { ...defaultSalePrefs(), landMin: 40, landMax: 80 }
  assert.deepEqual(
    saleMatches([cheap, mid, landHeavy, unknownShare], prefs).map((row) => row.address),
    ['2 B ST', '3 C ST'],
  )
})

test('typed sale numbers ignore $ and % marks', () => {
  assert.equal(parseSaleNumber(''), null)
  assert.equal(parseSaleNumber('$600,000'), 600000)
  assert.equal(parseSaleNumber('40%'), 40)
  assert.equal(saleCountLabel(1466), 'Show 1,466 for sale')
})
