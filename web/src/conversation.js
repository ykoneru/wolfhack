// Conversation state for the spoken assistant. Kept separate from the DOM so
// the trimming and prompt rules can be tested.

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

// Questions worth asking change once a home is on screen.
export function suggestedQuestions(home) {
  if (!home) {
    return [
      'Is Wake County assessing homes fairly?',
      'If I buy a $350,000 house, what assessment do I inherit?',
      'What does the price band chart show?',
    ]
  }
  return [
    'Is my assessment too high?',
    'How do I compare to my neighborhood?',
    'Should I appeal?',
  ]
}

// Read aloud, a reply works better as short spoken chunks than one block.
export function toParagraphs(reply) {
  return reply
    .split(/(?<=[.?!])\s+/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export function transcriptFromResults(results) {
  let finalText = ''
  let interimText = ''
  for (let i = 0; i < results.length; i += 1) {
    const result = results[i]
    const piece = result[0]?.transcript || ''
    if (result.isFinal) finalText += ` ${piece}`
    else interimText += ` ${piece}`
  }
  return {
    final: normalizeQuestion(finalText),
    interim: normalizeQuestion(interimText),
    heard: normalizeQuestion(`${finalText} ${interimText}`),
  }
}

// After the browser decides you have stopped talking: answer if there is a
// sentence, otherwise keep listening. Stop always returns to idle.
export function afterRecognitionEnded(live, heard) {
  if (!live) return 'idle'
  return heard ? 'thinking' : 'listening'
}

export function afterAssistantSpoke(live) {
  return live ? 'listening' : 'idle'
}

export function voiceStatus(state) {
  if (state === 'listening') return 'Listening — pause when you are done'
  if (state === 'thinking') return 'Thinking…'
  if (state === 'speaking') return 'Speaking…'
  return ''
}
