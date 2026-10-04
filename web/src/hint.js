import { HINT_COPY, HINT_STORAGE_KEY } from './config.js'

const FADE_MS = 200
let memoryDismissed = false
let leaving = false

function storage() {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

function wasDismissed() {
  if (memoryDismissed) return true
  const store = storage()
  return store?.getItem(HINT_STORAGE_KEY) === '1'
}

function rememberDismissed() {
  memoryDismissed = true
  storage()?.setItem(HINT_STORAGE_KEY, '1')
}

export function dismissHint() {
  const card = document.querySelector('#map-intro')
  if (!card || card.hidden || leaving) {
    rememberDismissed()
    return
  }
  rememberDismissed()
  leaving = true
  card.classList.add('is-leaving')
  window.setTimeout(() => {
    card.hidden = true
    card.classList.remove('is-leaving')
    leaving = false
  }, FADE_MS)
}

export function initHint() {
  const card = document.querySelector('#map-intro')
  if (!card) return
  document.querySelector('#hint-headline').textContent = HINT_COPY.headline
  document.querySelector('#hint-detail').textContent = HINT_COPY.detail
  if (wasDismissed()) {
    card.hidden = true
    return
  }
  card.hidden = false
  const close = document.querySelector('#dismiss-hint')
  close.addEventListener('click', dismissHint)
  card.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' && event.key !== 'Enter' && event.key !== ' ') return
    if (event.key === 'Escape' && event.target.closest('#panel, #chat-drawer')) return
    event.preventDefault()
    dismissHint()
  })
}
