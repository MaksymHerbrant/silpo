import { WebApp } from './telegram'

// Порожній рядок = той самий origin (бекенд роздає і статику Mini App).
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

let session = null

async function request(path, options = {}) {
  const { timeoutMs = 45000, ...init } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(BASE + path, {
      signal: controller.signal,
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
        ...(init.headers || {}),
      },
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      const err = new Error(text || res.statusText || `Помилка ${res.status}`)
      err.status = res.status
      throw err
    }
    return res.json()
  } finally {
    clearTimeout(timer)
  }
}

/** Вхід: initData валідується на бекенді через HMAC-SHA256 з токеном бота. */
export async function login() {
  const initData = WebApp.initData
  if (!initData) {
    throw new Error('Застосунок відкрито поза Telegram. Відкрийте його кнопкою меню бота.')
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

  getGoals: () => request('/goals'),
  saveGoals: (payload) => request('/goals', { method: 'POST', body: JSON.stringify(payload) }),

  agentContext: () => request('/agent/context'),
  agentStart: (prompt) =>
    request('/agent/run', { method: 'POST', body: JSON.stringify({ prompt: prompt || null }) }),
  agentStatus: () => request('/agent/run'),
  agentApply: () => request('/agent/apply', { method: 'POST', timeoutMs: 90000 }),
  shoppingList: () => request('/agent/shopping-list'),

  mcpLog: (limit = 60) => request(`/debug/mcp-log?limit=${limit}`),
}
