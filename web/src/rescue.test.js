import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRescueModel, formatClosing } from './rescue.js'

const fixture = name => JSON.parse(readFileSync(new URL(`../public/sample/${name}`, import.meta.url)))
const tracts = fixture('tracts.geojson').features
const sites = fixture('sites.geojson').features
const hours = fixture('hours.json')

test('rescue restores covered colors and counts overlapping population once', () => {
  const model = createRescueModel(tracts, sites, 3)
  const baseline = hours.by_hour[18]
  const one = model.scenario(baseline, 1)
  assert.equal(one.peopleSaved, 8400)
  assert.equal(one.uncovered_population, 8000)
  assert.equal(one.tracts['sample-south'].uncovered, false)
  assert.equal(one.tracts['sample-south'].covered, true)
  const three = model.scenario(baseline, 3)
  assert.equal(three.peopleSaved, 16400)
  assert.equal(three.uncovered_population, 0)
  assert.equal(three.picks.length, 2)
  assert.equal(model.scenario(baseline, 0).uncovered_population, 16400)
  assert.equal(baseline.tracts['sample-south'].uncovered, true, 'baseline must not be mutated')
  const duplicatePicks = { ...baseline, recommendations: { 3: [baseline.recommendations['1'][0], baseline.recommendations['1'][0]] } }
  assert.equal(model.scenario(duplicatePicks, 3).peopleSaved, 8400)
})

test('walking uses radius and arrival time, including closing equality and kept-open doors', () => {
  const library = { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0.04] }, properties: { id: 'library', name: 'Library', close_hour: 17 } }
  let model = createRescueModel([], [library], 3)
  let result = model.walk(0, 0, 16)
  assert.equal(result.withinRadius, true)
  assert.equal(result.beforeClose, true)
  assert.equal(model.walk(0, 0, 16.5).beforeClose, false)
  assert.equal(model.walk(0, 0, 18), null)
  assert.equal(model.walk(0, 0, 18, ['library']).beforeClose, true)
  assert.equal(model.walk(-0.1, 0, 16).withinRadius, false)
  library.properties.close_hour = result.arrivalHour
  model = createRescueModel([], [library], 3)
  assert.equal(model.walk(0, 0, 16).beforeClose, false, 'arriving exactly at closing is too late')
  assert.equal(formatClosing(null), 'Open 24 hours')
  assert.equal(formatClosing(17.5), '5:30 PM')
})

test('site impact and hospital walking are based on the same geometry', () => {
  const model = createRescueModel(tracts, sites, 3)
  assert.equal(model.siteImpact('sample-south-library', hours.by_hour[18]).additional, 8400)
  const result = model.walk(35.817, -78.703, 20)
  assert.equal(result.site.id, 'sample-rex-hospital')
  assert.equal(result.beforeClose, true)
  assert.equal(result.withinRadius, true)
})

test('statewide rescue agrees with marginal population in the pipeline recommendations', () => {
  const data = name => JSON.parse(readFileSync(new URL(`../public/${name}`, import.meta.url)))
  const model = createRescueModel(data('tracts.geojson').features, data('sites.geojson').features, 3)
  const hourly = data('hours.json')
  for (const hour of hourly.hours) for (const count of [1, 3, 5]) {
    const snapshot = hourly.by_hour[hour]
    const result = model.scenario(snapshot, count)
    assert.equal(result.peopleSaved, snapshot.recommendations[count].reduce((sum, p) => sum + p.people_added, 0))
  }
})
