import assert from 'node:assert/strict'
import test from 'node:test'

import {
  HISTORY_TURNS,
  MAX_QUESTION,
  afterAssistantSpoke,
  afterRecognitionEnded,
  normalizeQuestion,
  suggestedQuestions,
  toParagraphs,
  transcriptFromResults,
  trimHistory,
  voiceStatus,
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
  assert.equal(county.length, 3)
  assert.equal(home.length, 3)
  assert.match(county[0], /Wake County/)
  assert.match(home[0], /my assessment/)
  assert.notDeepEqual(county, home)
})

test('a spoken reply breaks into sentences', () => {
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

test('a recognition result keeps the final words and the words still coming', () => {
  const heard = transcriptFromResults([
    { isFinal: true, 0: { transcript: 'is my assessment' } },
    { isFinal: false, 0: { transcript: ' too high' } },
  ])
  assert.equal(heard.final, 'is my assessment')
  assert.equal(heard.interim, 'too high')
  assert.equal(heard.heard, 'is my assessment too high')
})

test('silence after talking keeps the loop open, stop ends it', () => {
  assert.equal(afterRecognitionEnded(true, 'is my assessment too high'), 'thinking')
  assert.equal(afterRecognitionEnded(true, ''), 'listening')
  assert.equal(afterRecognitionEnded(false, 'is my assessment too high'), 'idle')
  assert.equal(afterAssistantSpoke(true), 'listening')
  assert.equal(afterAssistantSpoke(false), 'idle')
})

test('the status line names the current step', () => {
  assert.equal(voiceStatus('listening'), 'Listening — pause when you are done')
  assert.equal(voiceStatus('idle'), '')
})
