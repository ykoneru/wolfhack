import assert from 'node:assert/strict'
import test from 'node:test'

import { addressMatches, canonicalAddress, normalizeAddress, queryForms } from './address.js'

test('normalize trims, lowercases, and collapses spaces', () => {
  assert.equal(normalizeAddress('  724   Toulouse  Ct.  '), '724 toulouse ct')
})

test('canonical form expands street abbreviations', () => {
  assert.equal(canonicalAddress('724 TOULOUSE CT'), '724 toulouse court')
  assert.equal(canonicalAddress('10105 Raven Tree Dr'), '10105 raven tree drive')
  assert.equal(canonicalAddress('100 Pond Bluff Way'), '100 pond bluff way')
})

test('Ct and Court match the same house', () => {
  assert.equal(addressMatches('724 Toulouse Ct', '724 TOULOUSE COURT', 'CARY'), true)
  assert.equal(addressMatches('724 toulouse court', '724 TOULOUSE CT', 'CARY'), true)
  assert.equal(addressMatches('725 Toulouse Ct', '724 TOULOUSE COURT', 'CARY'), false)
})

test('query forms include both the typed and expanded street', () => {
  const forms = queryForms('724 Toulouse Ct')
  assert.deepEqual(forms, ['724 toulouse ct', '724 toulouse court'])
})
