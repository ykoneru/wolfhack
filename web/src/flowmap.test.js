import test from 'node:test'
import assert from 'node:assert/strict'
import { bestHour, categoryFor, categoryShift, explanation, leaveAt, visitFits } from './flowmap.js'

const series = {
  16: { score: 61, category: 'Moderate', destinations: 20, commute: 8, weather: 0 },
  17: { score: 88, category: 'Very Busy', destinations: 28, commute: 10, weather: 0 },
  18: { score: 79, category: 'Busy', destinations: 24, commute: 8, weather: 0 },
  19: { score: 54, category: 'Moderate', destinations: 16, commute: 2, weather: 0 },
  20: { score: 39, category: 'Light', destinations: 10, commute: 0, weather: 0 },
  21: { score: 24, category: 'Quiet', destinations: 4, commute: 0, weather: 0 },
}

test('categories follow the published bands', () => {
  assert.equal(categoryFor(25), 'Quiet')
  assert.equal(categoryFor(26), 'Light')
  assert.equal(categoryFor(65), 'Moderate')
  assert.equal(categoryFor(66), 'Busy')
  assert.equal(categoryFor(81), 'Very Busy')
})

test('a closing place does not get the quietest hour if the visit will not fit', () => {
  const place = { open: 10, close: 21 }
  assert.equal(visitFits(20, 10, 21, 45), true)
  assert.equal(visitFits(21, 10, 21, 45), false)
  const chosen = bestHour(series, place, 16, 21, 45)
  assert.equal(chosen.hour, 20)
  assert.equal(chosen.score, 39)
})

test('leave time is the arrival hour minus the drive', () => {
  assert.equal(leaveAt(20, 18), '7:42 PM')
  assert.equal(leaveAt(9, 90), null)
})

test('a category change is stated in both hours', () => {
  const text = categoryShift(
    { label: '5:00 PM', score: 49, category: 'Moderate' },
    { label: '8:00 PM', score: 31, category: 'Light' },
  )
  assert.match(text, /Moderate/)
  assert.match(text, /Light/)
})

test('the explanation stays inside the computed scores', () => {
  const text = explanation({
    name: 'Crabtree Valley Mall',
    bestScore: 26.4,
    bestLabel: '8:00 PM',
    currentScore: 37.6,
    currentLabel: '5:00 PM',
    destinationsBest: 6,
    destinationsNow: 16,
    commuteBest: 0,
    commuteNow: 1.5,
    weatherBest: 0,
    weatherNow: 0,
    hoursSource: 'default',
  })
  assert.match(text, /26\.4/)
  assert.match(text, /37\.6/)
  assert.match(text, /category default/)
  assert.equal(text.includes('crowd'), false)
})
