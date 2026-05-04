/**
 * ChampIQ LakeB2B Connector — Background Service Worker
 *
 * Flow A: OAuth token capture (automatic on LinkedIn callback)
 * Flow B: Pairing token — reconnect LinkedIn session via extension
 * Flow C: LinkedIn company page post scraping — opens hidden tab, injects DOM extractor
 */

const CHAMPIQ_ORIGINS = [
  'champiq-production.up.railway.app',
  'localhost:3001',
  'localhost:5173',
  'localhost:5174',
  'localhost:5175',
  'localhost:5176',
  'localhost:4173',
  'localhost:8000',
]

function isChampIQTab(url) {
  return CHAMPIQ_ORIGINS.some(o => url.includes(o))
}

function extractHashParams(url) {
  try {
    const parsed = new URL(url)
    const hash = parsed.hash.startsWith('#') ? parsed.hash.slice(1) : parsed.hash
    const params = new URLSearchParams(hash)
    return {
      token: params.get('access_token') || params.get('token') || '',
      refreshToken: params.get('refresh_token') || '',
      pathname: parsed.pathname,
    }
  } catch {
    return { token: '', refreshToken: '', pathname: '' }
  }
}

function getLiAt() {
  return new Promise((resolve) => {
    chrome.cookies.getAll({ name: 'li_at' }, (cookies) => {
      const c = cookies.find(c => c.domain.includes('linkedin.com') && c.value && c.value.length > 20)
      resolve(c?.value || '')
    })
  })
}

function broadcastToChampIQ(message) {
  chrome.tabs.query({}, (tabs) => {
    for (const t of tabs) {
      if (t.id && t.url && isChampIQTab(t.url)) {
        chrome.tabs.sendMessage(t.id, message).catch(() => {})
      }
    }
  })
}

// ── Flow A: OAuth popup callback ──────────────────────────────────────────────

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  const url = changeInfo.url || tab.url
  if (!url) return
  if (!url.includes('access_token=') && !url.includes('token=')) return

  const { token, refreshToken, pathname } = extractHashParams(url)
  if (!token || token.length < 20) return
  if (!pathname.includes('/auth/callback') && !pathname.includes('/callback') && pathname !== '/login') return

  chrome.tabs.remove(tabId).catch(() => {})
  const li_at = await getLiAt()
  broadcastToChampIQ({ type: 'LAKEB2B_AUTH_TOKEN', token, refresh_token: refreshToken, li_at })
})

// ── Flow B + C: runtime messages ─────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'LAKEB2B_PING_BG') {
    sendResponse({ ok: true })
    return
  }

  if (msg.type === 'LAKEB2B_GET_LI_AT') {
    getLiAt().then((li_at) => {
      if (sender.tab?.id) {
        chrome.tabs.sendMessage(sender.tab.id, { type: 'LAKEB2B_LI_AT_VALUE', li_at, found: !!li_at }).catch(() => {})
      }
    })
    return
  }

  if (msg.type === 'LAKEB2B_PAIR') {
    const { pairing_token, api_base } = msg
    getLiAt().then(async (li_at) => {
      if (!li_at) {
        if (sender.tab?.id) {
          chrome.tabs.sendMessage(sender.tab.id, { type: 'LAKEB2B_PAIR_RESULT', success: false, error: 'LinkedIn li_at not found — log into LinkedIn first.' }).catch(() => {})
        }
        return
      }
      try {
        const res = await fetch(`${api_base}/api/integrations/extension/session-cookies`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Pairing-Token': pairing_token },
          body: JSON.stringify({ li_at }),
        })
        const data = await res.json().catch(() => ({}))
        if (sender.tab?.id) {
          chrome.tabs.sendMessage(sender.tab.id, { type: 'LAKEB2B_PAIR_RESULT', success: res.ok, user_name: data.user_name || null, error: res.ok ? null : (data.detail || `Error ${res.status}`) }).catch(() => {})
        }
      } catch (e) {
        if (sender.tab?.id) {
          chrome.tabs.sendMessage(sender.tab.id, { type: 'LAKEB2B_PAIR_RESULT', success: false, error: e.message }).catch(() => {})
        }
      }
    })
    return
  }

  // ── Flow C: Scrape LinkedIn company posts ─────────────────────────────────
  if (msg.type === 'SCRAPE_POSTS') {
    const { task_id, page_url, limit } = msg
    const senderTabId = sender.tab?.id ?? null

    openAndScrapeTab(page_url, limit ?? 20)
      .then((posts) => {
        const result = { type: 'SCRAPE_POSTS_RESULT', task_id, posts, status: 'ok' }
        broadcastToChampIQ(result)
        if (senderTabId) chrome.tabs.sendMessage(senderTabId, result).catch(() => {})
      })
      .catch((err) => {
        const result = { type: 'SCRAPE_POSTS_RESULT', task_id, posts: [], status: 'error', error: String(err?.message ?? err).slice(0, 300) }
        broadcastToChampIQ(result)
        if (senderTabId) chrome.tabs.sendMessage(senderTabId, result).catch(() => {})
      })
    return
  }
})

// ── Tab lifecycle ─────────────────────────────────────────────────────────────

async function openAndScrapeTab(pageUrl, limit) {
  const url = pageUrl.startsWith('http') ? pageUrl : `https://www.linkedin.com${pageUrl}`
  const tab = await chrome.tabs.create({ url, active: false })
  const tabId = tab.id

  try {
    await waitForTabLoad(tabId, 25_000)
    await sleep(3000)  // wait for React SPA hydration
    await injectAndScroll(tabId, limit)
    await sleep(2000)

    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: extractLinkedInPosts,
      args: [limit],
    })

    const posts = results?.[0]?.result ?? []
    return Array.isArray(posts) ? posts : []
  } finally {
    chrome.tabs.remove(tabId).catch(() => {})
  }
}

function waitForTabLoad(tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    const deadline = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener)
      reject(new Error('Tab load timed out'))
    }, timeoutMs)

    function listener(id, info) {
      if (id !== tabId) return
      if (info.status === 'complete') {
        clearTimeout(deadline)
        chrome.tabs.onUpdated.removeListener(listener)
        resolve()
      }
    }
    chrome.tabs.onUpdated.addListener(listener)
    chrome.tabs.get(tabId, (t) => {
      if (t?.status === 'complete') {
        clearTimeout(deadline)
        chrome.tabs.onUpdated.removeListener(listener)
        resolve()
      }
    })
  })
}

async function injectAndScroll(tabId, limit) {
  const scrollCount = Math.ceil(limit / 3) + 3
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (count) => new Promise((resolve) => {
      let i = 0
      function step() {
        window.scrollBy(0, 900)
        i++
        if (i < count) setTimeout(step, 800)
        else resolve(undefined)
      }
      step()
    }),
    args: [scrollCount],
  })
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

// ── DOM extractor — injected into the LinkedIn tab ────────────────────────────
// Runs inside the LinkedIn page context. Must be fully self-contained.

function extractLinkedInPosts(limit) {
  function norm(v) {
    return String(v ?? '').replace(/\s+/g, ' ').trim()
  }

  function textOf(root, ...selectors) {
    for (const sel of selectors) {
      try {
        const el = root.querySelector(sel)
        if (el && norm(el.textContent).length > 0) return norm(el.textContent)
      } catch (_) {}
    }
    return ''
  }

  function allText(root, ...selectors) {
    for (const sel of selectors) {
      try {
        const els = Array.from(root.querySelectorAll(sel))
        const joined = els.map(e => norm(e.textContent)).filter(Boolean).join(' ')
        if (joined.length > 0) return joined
      } catch (_) {}
    }
    return ''
  }

  function hrefOf(root, ...selectors) {
    for (const sel of selectors) {
      try {
        const el = root.querySelector(sel)
        if (el && el.href) return el.href
      } catch (_) {}
    }
    return ''
  }

  function parseMetric(v) {
    const raw = norm(v).toLowerCase().replace(/,/g, '').replace(/\s/g, '')
    const m = raw.match(/(\d+(?:\.\d+)?)(k|m)?/)
    if (!m) return 0
    const base = Number(m[1])
    const s = (m[2] || '').toLowerCase()
    if (s === 'k') return Math.round(base * 1000)
    if (s === 'm') return Math.round(base * 1_000_000)
    return Math.round(base)
  }

  const CONTAINERS = [
    '.scaffold-finite-scroll__content',
    '.feed-following-feed',
    '.profile-creator-shared-feed-update__container',
    '[data-finite-scroll-hotkey-context]',
    'main .scaffold-layout__main',
    'main',
  ]
  let container = document.body
  for (const sel of CONTAINERS) {
    const el = document.querySelector(sel)
    if (el) { container = el; break }
  }

  const POST_SELECTORS = [
    '[data-urn*="activity"]',
    '[data-urn*="ugcPost"]',
    '[data-urn*="share"]',
    '.feed-shared-update-v2',
    '.occludable-update',
    '[data-urn]',
  ]

  let postEls = []
  for (const sel of POST_SELECTORS) {
    try {
      const found = Array.from(container.querySelectorAll(sel)).filter(el => {
        const urn = el.getAttribute('data-urn') || ''
        if (urn && !urn.includes('activity') && !urn.includes('ugcPost') && !urn.includes('share') && !urn.includes('update')) return false
        return el.offsetHeight > 80
      })
      if (found.length > 0) { postEls = found; break }
    } catch (_) {}
  }

  const seen = new Set()
  const posts = []

  for (const el of postEls) {
    if (posts.length >= limit) break

    const author = textOf(el,
      '.update-components-actor__name span[aria-hidden="true"]',
      '.update-components-actor__name',
      '.feed-shared-actor__name',
      '[data-anonymize="person-name"]',
      'h3', 'strong',
    )

    const text = textOf(el,
      '.update-components-text span[dir]',
      '.update-components-text',
      '.feed-shared-update-v2__description span[dir]',
      '.feed-shared-update-v2__description',
      '.attributed-text-segment-list__content',
      '.update-components-article__meta-description',
    ) || allText(el, '.break-words', 'p[dir]', '[dir="ltr"]')

    const url = hrefOf(el,
      'a[href*="/feed/update/urn"]',
      'a[href*="activity"]',
      'time a',
      '.update-components-actor__sub-description a',
    )

    const posted_at = textOf(el,
      '.update-components-actor__sub-description span[aria-hidden="true"]',
      '.update-components-actor__sub-description',
      '.feed-shared-actor__sub-description',
      'time',
    )

    const author_url = hrefOf(el,
      '.update-components-actor__meta a',
      '.update-components-actor__image a',
      '.feed-shared-actor__container-link',
    )

    const headline = textOf(el,
      '.update-components-actor__description span[aria-hidden="true"]',
      '.update-components-actor__description',
      '.feed-shared-actor__description',
    )

    const reactionsText = textOf(el,
      '.social-details-social-counts__reactions-count',
      'button[aria-label*="reaction"] span',
      'button[aria-label*="React"] span',
      '.social-counts-reactions__count',
    )

    const commentsText = textOf(el,
      '.social-details-social-counts__comments',
      '.social-details-social-counts__comments a span',
      'button[aria-label*="comment"] span',
      'button[aria-label*="Comment"] span',
    )

    const urn = el.getAttribute('data-urn') || ''
    const id = urn || url || (author && text ? `${author}::${posted_at}::${text.slice(0, 100)}` : '')

    if (!id && !text && !author) continue
    if (seen.has(id || text.slice(0, 60))) continue
    seen.add(id || text.slice(0, 60))

    posts.push({
      id,
      author: author || 'Unknown',
      author_url,
      headline,
      text: text || '[No text content]',
      posted_at,
      reactions: parseMetric(reactionsText),
      comments: parseMetric(commentsText),
      url,
    })
  }

  // If nothing found, return one diagnostic entry so we can tell whether
  // the page loaded at all vs the selectors failed
  if (posts.length === 0) {
    return [{
      _diagnostic: true,
      url: location.href,
      title: document.title.slice(0, 100),
      bodyTextLen: (document.body?.textContent || '').length,
      dataUrnCount: document.querySelectorAll('[data-urn]').length,
      anyPostClassCount: document.querySelectorAll('.feed-shared-update-v2, .occludable-update').length,
      hasLoginForm: !!document.querySelector('input[name="session_password"], a[href*="login"], a[href*="signup"]'),
    }]
  }

  return posts
}
