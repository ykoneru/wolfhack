import { STREET_EXPAND } from './config.js'

export function normalizeAddress(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[.,#]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function canonicalAddress(value) {
  const tokens = normalizeAddress(value).split(' ').filter(Boolean)
  return tokens.map((token) => STREET_EXPAND[token] || token).join(' ')
}

export function queryForms(value) {
  const normalized = normalizeAddress(value)
  const canonical = canonicalAddress(value)
  const forms = new Set()
  if (normalized) forms.add(normalized)
  if (canonical) forms.add(canonical)
  return [...forms]
}

export function addressMatches(query, address, city = '') {
  const needle = canonicalAddress(query)
  if (!needle) return false
  const haystack = canonicalAddress(`${address} ${city}`)
  return haystack.includes(needle)
}
