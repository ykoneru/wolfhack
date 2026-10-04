const tabs = [...document.querySelectorAll('[role="tab"]')]
const sheet = document.querySelector('#panel')
export function activateTab(name, focus = false) {
  if (!sheet.open) sheet.show()
  for (const tab of tabs) {
    const selected = tab.id === `tab-${name}`
    tab.setAttribute('aria-selected', String(selected))
    tab.tabIndex = selected ? 0 : -1
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected
    if (selected && focus) tab.focus()
  }
  document.querySelector('.panel-scroll').scrollTop = 0
  document.querySelector('[data-search]').classList.remove('rail-active')
  document.querySelectorAll('[data-open]').forEach(button => button.classList.toggle('rail-active', button.dataset.open === name))
}

for (const [index, tab] of tabs.entries()) {
  tab.addEventListener('click', () => activateTab(tab.id.slice(4)))
  tab.addEventListener('keydown', (event) => {
    let next
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
    if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = tabs.length - 1
    if (next === undefined) return
    event.preventDefault()
    activateTab(tabs[next].id.slice(4), true)
  })
}
let detailTrigger = null
for (const button of document.querySelectorAll('[data-open]')) {
  button.addEventListener('click', () => {
    detailTrigger = button
    activateTab(button.dataset.open, true)
  })
}
function closeDetails() {
  sheet.close()
  document.querySelector('[data-search]').classList.add('rail-active')
  document.querySelectorAll('[data-open]').forEach(button => button.classList.remove('rail-active'))
  detailTrigger?.focus()
}
document.querySelector('#close-details').addEventListener('click', closeDetails)
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && sheet.open && !drawer.open) closeDetails()
})
document.querySelector('[data-search]').addEventListener('click', () => {
  closeDetails()
  document.querySelector('#search').focus()
})
let chatTrigger = null
const drawer = document.querySelector('#chat-drawer')
for (const button of document.querySelectorAll('[data-chat], #open-chat')) button.addEventListener('click', () => {
  chatTrigger = button
  drawer.showModal()
  document.querySelector('#question').focus()
})
document.querySelector('#close-chat').addEventListener('click', () => drawer.close())
drawer.addEventListener('close', () => {
  const stop = document.querySelector('#stop-talk')
  if (!stop.hidden) stop.click()
  chatTrigger?.focus()
})
