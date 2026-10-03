import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { TRACT_COLORS, tractColor, validateHours, createPlayback } from './hours.js'

const fixture = name => JSON.parse(readFileSync(new URL(`../public/sample/${name}`, import.meta.url)))

test('sample turns red when doors close; the hospital tract retains coverage', () => {
  const data = validateHours(fixture('hours.json'), fixture('tracts.geojson').features)
  assert.equal(data.by_hour[14].uncovered_population, 0)
  assert.equal(data.by_hour[18].uncovered_population, 16400)
  assert.equal(tractColor(data.by_hour[14].tracts['sample-south']), TRACT_COLORS.covered)
  assert.equal(tractColor(data.by_hour[18].tracts['sample-south']), TRACT_COLORS.uncovered)
  assert.equal(tractColor(data.by_hour[18].tracts['sample-rex']), TRACT_COLORS.covered)
  assert.equal(tractColor({ exposed: false, covered: true, uncovered: false }), TRACT_COLORS.neutral)
})

test('rejects mismatched IDs, missing hours and incorrect population instead of showing false totals', () => {
  const features = fixture('tracts.geojson').features
  const data = fixture('hours.json')
  delete data.by_hour[18].tracts['sample-south']
  assert.throws(() => validateHours(data, features))
  const missing = fixture('hours.json')
  delete missing.by_hour[17]
  assert.throws(() => validateHours(missing, features))
  const wrongTotal = fixture('hours.json')
  wrongTotal.by_hour[18].uncovered_population = 1
  assert.throws(() => validateHours(wrongTotal, features))
})

test('Play runs 4–7 PM, stops at 7 PM and restarts cleanly', () => {
  const rendered = []
  let tick
  let cancelled = 0
  const player = createPlayback(h => rendered.push(h), {
    schedule(callback) { tick = callback; return 1 },
    cancel() { cancelled++ },
  })
  player.play()
  tick(); tick(); tick()
  assert.deepEqual(rendered, [16, 17, 18, 19])
  assert.equal(player.isPlaying(), false)
  assert.equal(cancelled, 1)
  player.play()
  assert.equal(rendered.at(-1), 16)
  player.pause()
  assert.equal(player.isPlaying(), false)
  assert.equal(cancelled, 2)
})
