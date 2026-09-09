import { WebApp } from './telegram'

// Порожній рядок = той самий origin (бекенд роздає і статику Mini App).
// undefined (змінної немає) = локальна розробка з vite dev на іншому порту.
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

let session = null

async function request(path, options = {}) {
  // Перерахунок профілю тягне десятки викликів MCP — даємо йому окремий,
  // великий таймаут, решта запитів мають лишатись швидкими.
  const { timeoutMs = 45000, ...init } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await send(path, init, controller.signal)
  } finally {
    clearTimeout(timer)
  }
}

async function send(path, options, signal) {
  const res = await fetch(BASE + path, {
    signal,
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    const err = new Error(text || res.statusText || `Помилка ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

/** Логін: initData валідується на бекенді через HMAC-SHA256 з bot token. */
export async function login() {
  const initData = WebApp.initData
  if (!initData) {
    throw new Error(
      'Застосунок відкрито поза Telegram: немає initData. Відкрийте Mini App через бота.',
    )
  }
  session = await request('/auth/telegram', {
    method: 'POST',
    body: JSON.stringify({ init_data: initData }),
  })
  return session
}

export const api = {
  silpoStatus: () => request('/auth/silpo/status'),
  silpoStart: () => request('/auth/silpo/start', { method: 'POST' }),
  cartAnalysis: () => request('/cart/analysis'),
  allergens: () => request('/cart/allergens'),
  trends: (refresh = false) => request(`/trends/weekly?refresh=${refresh}`),
  rebuildTrends: () => request('/trends/rebuild', { method: 'POST' }),
  swaps: (rebuild = true, source = 'both') =>
    request(`/swaps/suggestions?rebuild=${rebuild}&source=${source}`),
  applySwap: (id) => request(`/swaps/${id}/apply`, { method: 'POST' }),
  declineSwap: (id) => request(`/swaps/${id}/decline`, { method: 'POST' }),
  sendReport: () => request('/bot/report', { method: 'POST' }),
  mcpLog: (limit = 50) => request(`/debug/mcp-log?limit=${limit}`),
  mcpTools: () => request('/debug/tools'),
}
