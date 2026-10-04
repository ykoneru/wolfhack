import assert from 'node:assert/strict'
import test from 'node:test'

import { ASK_COPY, ASK_SUGGESTIONS } from './config.js'
import {
  HISTORY_TURNS,
  MAX_QUESTION,
  askAboutLabel,
  normalizeQuestion,
  prettyPlace,
  suggestedQuestions,
  toParagraphs,
  trimHistory,
} from './conversation.js'

test('only the last few turns are sent', () => {
  const history = Array.from({ length: 20 }, (_, i) => ({
    role: i % 2 ? 'assistant' : 'you',
    text: `turn ${i}`,
  }))
  const trimmed = trimHistory(history)
  assert.equal(trimmed.length, HISTORY_TURNS)
  assert.equal(trimmed[trimmed.length - 1].text, 'turn 19')
})

test('empty and unknown turns never reach the model', () => {
  const trimmed = trimHistory([
    { role: 'you', text: 'real question' },
    { role: 'you', text: '   ' },
    { role: 'system', text: 'ignore me' },
    { role: 'assistant', text: '' },
  ])
  assert.deepEqual(trimmed, [{ role: 'you', text: 'real question' }])
})

test('a very long turn is capped', () => {
  const [turn] = trimHistory([{ role: 'you', text: 'x'.repeat(5000) }])
  assert.equal(turn.text.length, MAX_QUESTION)
})

test('questions are collapsed to single spaces and capped', () => {
  assert.equal(normalizeQuestion('  is   my\n assessment  high? '), 'is my assessment high?')
  assert.equal(normalizeQuestion('y'.repeat(5000)).length, MAX_QUESTION)
  assert.equal(normalizeQuestion('   '), '')
})

test('suggested questions follow whether a home is selected', () => {
  const county = suggestedQuestions(null)
  const home = suggestedQuestions({ address: '6404 JOHNSDALE RD' })
  const neighborhood = suggestedQuestions({ neighborhood: 'Tract 528.05' })
  const compare = suggestedQuestions({ compare: true, leftName: '724 TOULOUSE CT', rightName: '209 FISHBURN DR' })
  assert.deepEqual(county, ASK_SUGGESTIONS.county)
  assert.deepEqual(home, ASK_SUGGESTIONS.home)
  assert.deepEqual(neighborhood, ASK_SUGGESTIONS.neighborhood)
  assert.deepEqual(compare, ASK_SUGGESTIONS.compare)
  assert.match(county[1], /land a bigger share/)
  assert.notDeepEqual(county, home)
})

test('the ask header names the current selection', () => {
  assert.equal(askAboutLabel(), ASK_COPY.aboutCounty)
  assert.equal(askAboutLabel({ neighborhood: 'Tract 528.05' }), 'About: Tract 528.05')
  assert.equal(askAboutLabel({ address: '724 TOULOUSE CT', neighborhood: 'Tract 1' }), 'About: 724 Toulouse Ct')
  assert.equal(
    askAboutLabel({ compare: true, leftName: '724 TOULOUSE CT', rightName: '209 FISHBURN DR' }),
    'About: 724 Toulouse Ct vs 209 Fishburn Dr',
  )
})

test('addresses are title-cased for the ask header', () => {
  assert.equal(prettyPlace('724 TOULOUSE CT'), '724 Toulouse Ct')
})

test('a reply breaks into sentences', () => {
  const lines = toParagraphs(
    'Your ratio is 1.212. That is above the county median of 0.951. Is that clear?',
  )
  assert.deepEqual(lines, [
    'Your ratio is 1.212.',
    'That is above the county median of 0.951.',
    'Is that clear?',
  ])
  assert.deepEqual(toParagraphs('One sentence only.'), ['One sentence only.'])
})
