const sheet = document.querySelector('#panel')
const drawer = document.querySelector('#chat-drawer')
const askTriggers = [...document.querySelectorAll('[data-chat]')]
const expandButton = document.querySelector('#ask-expand')
const NARROW = window.matchMedia('(max-width: 899px)')

function syncDetailsOpen() {
  document.body.classList.toggle('details-open', Boolean(sheet.open))
}

export function openDetails() {
  document.querySelector('#close-for-sale')?.click()
  if (!sheet.open) sheet.show()
  syncDetailsOpen()
  document.querySelector('[data-search]').classList.remove('rail-active')
  const body = document.querySelector('#panel-content')
  if (body) body.scrollTop = 0
}

export function closeDetails() {
  sheet.close()
  syncDetailsOpen()
  document.querySelector('[data-search]').classList.add('rail-active')
}
document.querySelector('#close-details').addEventListener('click', closeDetails)
sheet.addEventListener('close', syncDetailsOpen)
syncDetailsOpen()
document.querySelector('[data-search]').addEventListener('click', () => {
  closeDetails()
  document.querySelector('#close-for-sale')?.click()
  document.querySelector('#search').focus()
})

let chatTrigger = null
let handleStartY = 0
let handleDragging = false

export function isAskOpen() {
  return drawer.classList.contains('is-open')
}

function syncAskRole() {
  if (NARROW.matches) {
    drawer.setAttribute('role', 'dialog')
    drawer.setAttribute('aria-modal', 'false')
  } else {
    drawer.setAttribute('role', 'complementary')
    drawer.removeAttribute('aria-modal')
    drawer.classList.remove('is-expanded')
    expandButton?.setAttribute('aria-label', 'Expand ask panel')
  }
}

function syncAskTriggers(open) {
  askTriggers.forEach((button) => button.setAttribute('aria-expanded', String(open)))
}

export function openAsk(trigger) {
  if (trigger) chatTrigger = trigger
  document.querySelector('#close-for-sale')?.click()
  syncAskRole()
  drawer.hidden = false
  drawer.inert = false
  drawer.classList.add('is-open')
  drawer.setAttribute('aria-hidden', 'false')
  document.body.classList.add('ask-open')
  syncAskTriggers(true)
  requestAnimationFrame(() => document.querySelector('#question')?.focus())
}

export function closeAsk() {
  if (!isAskOpen()) return
  drawer.dispatchEvent(new Event('askclose'))
  drawer.classList.remove('is-open', 'is-expanded')
  drawer.setAttribute('aria-hidden', 'true')
  document.body.classList.remove('ask-open')
  drawer.inert = true
  drawer.hidden = true
  syncAskTriggers(false)
  expandButton?.setAttribute('aria-label', 'Expand ask panel')
  chatTrigger?.focus()
}

function toggleAskExpanded() {
  if (!NARROW.matches || !isAskOpen()) return
  const expanded = !drawer.classList.contains('is-expanded')
  drawer.classList.toggle('is-expanded', expanded)
  expandButton?.setAttribute('aria-label', expanded ? 'Shrink ask panel' : 'Expand ask panel')
}

for (const button of askTriggers) {
  button.addEventListener('click', () => openAsk(button))
}
document.querySelector('#close-chat').addEventListener('click', closeAsk)
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return
  if (isAskOpen()) {
    event.preventDefault()
    closeAsk()
    return
  }
  if (sheet.open) closeDetails()
})
NARROW.addEventListener('change', syncAskRole)
drawer.inert = true
syncAskRole()

expandButton?.addEventListener('click', (event) => {
  if (handleDragging) return
  event.preventDefault()
  toggleAskExpanded()
})
expandButton?.addEventListener('pointerdown', (event) => {
  if (!NARROW.matches) return
  handleDragging = false
  handleStartY = event.clientY
  expandButton.setPointerCapture(event.pointerId)
})
expandButton?.addEventListener('pointermove', (event) => {
  if (!expandButton.hasPointerCapture(event.pointerId)) return
  const dy = event.clientY - handleStartY
  if (Math.abs(dy) > 8) handleDragging = true
})
expandButton?.addEventListener('pointerup', (event) => {
  if (!expandButton.hasPointerCapture(event.pointerId) && !handleDragging) return
  const dy = event.clientY - handleStartY
  if (dy < -40) {
    drawer.classList.add('is-expanded')
    expandButton.setAttribute('aria-label', 'Shrink ask panel')
  } else if (dy > 80 && !drawer.classList.contains('is-expanded')) {
    closeAsk()
  } else if (dy > 40) {
    drawer.classList.remove('is-expanded')
    expandButton.setAttribute('aria-label', 'Expand ask panel')
  }
  window.setTimeout(() => {
    handleDragging = false
  }, 0)
})
