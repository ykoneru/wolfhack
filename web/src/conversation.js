// Conversation state for Ask. Kept separate from the DOM so the trimming and
// prompt rules can be tested.

import { ASK_COPY, ASK_SUGGESTIONS } from './config.js'

export const HISTORY_TURNS = 6
export const MAX_QUESTION = 400

// Only the last few turns travel to the model, so a long chat cannot push the
// data block out of the prompt.
export function trimHistory(history) {
  return history
    .filter((turn) => (turn.role === 'you' || turn.role === 'assistant') && turn.text?.trim())
    .slice(-HISTORY_TURNS)
    .map((turn) => ({ role: turn.role, text: turn.text.trim().slice(0, MAX_QUESTION) }))
}

export function normalizeQuestion(question) {
  return question.replace(/\s+/g, ' ').trim().slice(0, MAX_QUESTION)
}

export function prettyPlace(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b([a-z])/g, (letter) => letter.toUpperCase())
}

export function askAboutLabel(context = {}) {
  if (context.compare) {
    const left = context.leftName ? prettyPlace(context.leftName) : ''
    const right = context.rightName ? prettyPlace(context.rightName) : ''
    if (left && right) return `About: ${left} vs ${right}`
    if (left) return `About: ${left} and a second home`
    return 'About: this comparison'
  }
  if (context.address) return `About: ${prettyPlace(context.address)}`
  if (context.neighborhood) return `About: ${context.neighborhood}`
  return ASK_COPY.aboutCounty
}

// Questions worth asking change once a home, comparison, or neighborhood is on screen.
export function suggestedQuestions(context) {
  if (context?.compare) return [...ASK_SUGGESTIONS.compare]
  if (context?.address) return [...ASK_SUGGESTIONS.home]
  if (context?.neighborhood) return [...ASK_SUGGESTIONS.neighborhood]
  return [...ASK_SUGGESTIONS.county]
}

export function toParagraphs(reply) {
  return reply
    .split(/(?<=[.?!])\s+/)
    .map((line) => line.trim())
    .filter(Boolean)
}
