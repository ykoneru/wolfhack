// Tunable thresholds and copy. Keep these here so the map and flags stay consistent.

export const MIN_TRACT_HOMES = 25

export const CAUTION = {
  highLandShare: 0.8,
  lowLandShare: 0.1,
  newConstructionYears: 2,
  oldYear: 1975,
  buildingVsLand: 0.25,
  neighborhoodBuildingRatio: 0.5,
}

export const MAP_VIEW = {
  flyZoom: 17,
  minZoom: 9,
  maxBoundsPad: 0.18,
  hideHighlightBelowZoom: 12,
  hidePointsBelowZoom: 14,
  paddingTopLeft: [16, 16],
  paddingBottomRight: [16, 16],
  wakeBounds: [
    [35.52, -78.98],
    [36.06, -78.25],
  ],
}

export const LOT_PREVIEW = {
  tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  attribution: 'Esri',
  zoom: 19,
  caption: 'Aerial of this parcel. Roof and lot, not a street photo.',
}

export const SEARCH_COPY = {
  notFound: 'No Wake County house matches that address. Check the number, or try a nearby street.',
  error: 'Search could not reach the county lookup.',
  pick: 'Multiple matches. Pick one.',
}

export const HINT_COPY = {
  headline: 'How much of your home is actually land?',
  detail: 'Search any Wake County address, or click a neighborhood, to see how its assessed value splits between land and building.',
}

export const HINT_STORAGE_KEY = 'houseOrLotHintDismissed'

export const ASK_COPY = {
  title: 'Ask Parcel',
  aboutCounty: 'About: Wake County',
  suggestionsPrompt: 'Try one of these',
  placeholder: 'Ask anything about the numbers',
  send: 'Send',
  retry: 'Retry',
  close: 'Close ask',
  expand: 'Expand ask panel',
  collapse: 'Shrink ask panel',
  error: 'The assistant is unreachable. Check that the API is running.',
}

export const ASK_SUGGESTIONS = {
  county: [
    'What is Wake County’s typical land share?',
    'Where in Wake County is land a bigger share of value?',
    'What does teardown watch mean?',
  ],
  neighborhood: [
    'What is this neighborhood’s typical land share?',
    'How does this compare with Wake County?',
    'What does teardown watch mean here?',
  ],
  home: [
    'Am I buying a house or a lot?',
    'How does this compare to my neighborhood?',
    'Would a remodel pay off here?',
  ],
  compare: [
    'Which of these is more of a lot?',
    'How do their land shares differ?',
    'Is the assessed gap mostly size?',
  ],
}

export const DISCLAIMER =
  'These are 2024 assessed values, not a sale price or what a buyer would pay for the lot.'

export const FOR_SALE = {
  title: 'For sale',
  lead: 'Filter the cached listings by list price and land share.',
  reset: 'Reset',
  show: (count) => `Show ${Number(count).toLocaleString('en-US')} for sale`,
  empty: 'No cached listings',
}

export const COMPARE = {
  title: 'Compare',
  lead: 'Search two addresses, a neighborhood, or Wake County typical.',
  placeholder: 'Search the first address',
  placeholderSecond: 'Search the second address',
  placeholderMore: 'Search another address to replace the second home',
  empty: 'Type it in the search box above, then pick a match.',
  emptySecond: 'Type it in the search box above, then pick a match.',
  firstSlot: 'First home',
  secondSlot: 'Second home',
  addFirst: 'Add the first address',
  addSecond: 'Add a second address',
  theCall: 'The call',
  whatThatMeans: 'What that means',
  countyName: 'Wake County typical',
  countyQueries: [
    'county',
    'county typical',
    'county average',
    'wake county',
    'wake county typical',
    'wake typical',
  ],
  sameShare: 'Same land share.',
  sameAssessed: (left, right) => `${left} and ${right} have the same assessed total.`,
  listingNote: 'A list price is not the county land and building split. Assessments are not market prices.',
  cautionTitle: 'Interpret with caution',
  landLabel: 'Land',
  buildingLabel: 'Building',
  totalLabel: 'Total assessed',
  buildingPerSqft: 'Building value / sq ft',
  heatedLabel: 'Heated area',
  lotLabel: 'Lot size',
  landShareLabel: 'Land share',
  landPerAcre: 'Land value / acre',
  landPerSqft: 'Land value / sq ft',
  sizeGapBand: 0.05,
  land: '#c9a227',
  building: '#8b8c94',
  axisHomeA: '#202124',
  axisHomeB: '#c92532',
  axisNeighborhood: '#7c7d86',
  axisCounty: '#c9a227',
  builtPrefix: 'built',
  export: 'Export',
  vs: (name) => `Difference vs ${name}`,
  mostlySize: (leftSq, rightSq) =>
    `Building value per square foot is about the same, so the gap is mostly size (${leftSq} vs ${rightSq} sq ft).`,
}

export const EXPORT = {
  accent: '#C62828',
  building: '#1c1c1e',
  paper: '#ffffff',
  ink: '#202124',
  muted: '#62646e',
  line: '#e6e6ea',
  caution: '#fff6e8',
  typicalBand: 0.05,
  publicUrl: '',
  roll: 'Wake County 2024 roll',
  moreHouse: 'More house than typical',
  aboutTypical: 'About typical',
  moreLand: 'More land than typical',
  source: 'Wake County 2024 assessed land and building values.',
  method: 'How the split is calculated: Method page in Parcel.',
  listingNote: 'A list price is not the county land and building split. Assessments are not market prices.',
  cautionTitle: 'Interpret with caution',
}

export const STREET_EXPAND = {
  ct: 'court',
  court: 'court',
  dr: 'drive',
  drive: 'drive',
  st: 'street',
  street: 'street',
  ave: 'avenue',
  avenue: 'avenue',
  blvd: 'boulevard',
  boulevard: 'boulevard',
  ln: 'lane',
  lane: 'lane',
  rd: 'road',
  road: 'road',
  pl: 'place',
  place: 'place',
  cir: 'circle',
  circle: 'circle',
  ter: 'terrace',
  terrace: 'terrace',
  hwy: 'highway',
  highway: 'highway',
  pkwy: 'parkway',
  parkway: 'parkway',
  trl: 'trail',
  trail: 'trail',
  way: 'way',
}
