// Filter cached for-sale listings by list price and land share.
// Empty fields mean no filter, so the full cached set stays visible.

export function defaultSalePrefs() {
  return {
    priceMin: null,
    priceMax: null,
    landMin: null,
    landMax: null,
  }
}

export function parseSaleNumber(value) {
  if (value == null) return null
  const cleaned = String(value).replace(/[$,%\s]/g, '')
  if (!cleaned) return null
  const amount = Number(cleaned)
  return Number.isFinite(amount) ? amount : null
}

export function landFilterIsOpen(prefs) {
  const min = prefs?.landMin
  const max = prefs?.landMax
  if (min == null && max == null) return true
  return (min == null || min <= 0) && (max == null || max >= 100)
}

export function priceFilterIsOpen(prefs) {
  return prefs?.priceMin == null && prefs?.priceMax == null
}

export function passesSaleFilters(listing, prefs) {
  const price = Number(listing?.price)
  const hasPrice = Number.isFinite(price)
  if (prefs.priceMin != null && (!hasPrice || price < prefs.priceMin)) return false
  if (prefs.priceMax != null && (!hasPrice || price > prefs.priceMax)) return false
  if (landFilterIsOpen(prefs)) return true
  const share = Number(listing?.land_share)
  if (!Number.isFinite(share)) return false
  const percent = share * 100
  const low = prefs.landMin == null ? 0 : prefs.landMin
  const high = prefs.landMax == null ? 100 : prefs.landMax
  return percent >= Math.min(low, high) && percent <= Math.max(low, high)
}

export function saleMatches(listings, prefs) {
  return (listings || []).filter((row) => passesSaleFilters(row, prefs))
}

export function saleCountLabel(count) {
  const n = Number(count) || 0
  return `Show ${n.toLocaleString('en-US')} for sale`
}
