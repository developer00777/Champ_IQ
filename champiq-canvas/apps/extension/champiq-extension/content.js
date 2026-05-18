/**
 * ChampIQ LakeB2B Connector — Content Script
 *
 * Bridges window.postMessage (ChampIQ page) ↔ chrome.runtime (background.js).
 *
 * MV3 note: chrome.runtime.sendMessage returns a Promise in Chrome 99+.
 * If the service worker is sleeping or the port closes before it wakes,
 * the Promise rejects with "The message port closed before a response was
 * received". This is expected and harmless — we suppress it with .catch(()=>{})
 * on every sendMessage call so it never surfaces as an uncaught error.
 */

function send(msg) {
  try {
    chrome.runtime.sendMessage(msg).catch(() => {})
  } catch (_) {
    // Extension context invalidated after reload — silently ignore
  }
}

// Page → background
window.addEventListener('message', (ev) => {
  if (!ev.data) return

  if (ev.data.type === 'LAKEB2B_PING') {
    window.postMessage({ type: 'LAKEB2B_PONG' }, '*')
  }

  if (ev.data.type === 'LAKEB2B_PAIR') {
    send({ type: 'LAKEB2B_PAIR', pairing_token: ev.data.pairing_token, api_base: ev.data.api_base })
  }

  if (ev.data.type === 'LAKEB2B_GET_LI_AT') {
    send({ type: 'LAKEB2B_GET_LI_AT' })
  }

  if (ev.data.type === 'SCRAPE_POSTS') {
    send({ type: 'SCRAPE_POSTS', task_id: ev.data.task_id, page_url: ev.data.page_url, limit: ev.data.limit ?? 20 })
  }
})

// Background → page: forward all result messages back to the ChampIQ page
chrome.runtime.onMessage.addListener((msg) => {
  if (
    msg.type === 'LAKEB2B_AUTH_TOKEN' ||
    msg.type === 'LAKEB2B_LI_AT_VALUE' ||
    msg.type === 'LAKEB2B_PAIR_RESULT' ||
    msg.type === 'SCRAPE_POSTS_RESULT'
  ) {
    window.postMessage(msg, '*')
  }
})
