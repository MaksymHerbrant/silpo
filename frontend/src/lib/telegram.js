/**
 * Обгортка над офіційним telegram-web-app.js (підключений в index.html).
 *
 * Свідомо БЕЗ @twa-dev/sdk: він тягне власну копію того самого скрипта, і
 * дві копії конкурують за location.hash, з якого Telegram передає tgWebAppData.
 * Через це initData міг приходити пошкодженим — і підпис HMAC не сходився.
 */
const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined

export const WebApp = tg || {
  // Фолбек для запуску в звичайному браузері (щоб нічого не падало)
  initData: '',
  themeParams: {},
  colorScheme: 'light',
  ready() {},
  expand() {},
  onEvent() {},
  openLink(url) { window.open(url, '_blank') },
  MainButton: {
    setText() {}, onClick() {}, offClick() {},
    show() {}, hide() {}, showProgress() {}, hideProgress() {},
  },
  HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
}

/** Прокидає themeParams Telegram у CSS-змінні, щоб застосунок жив у темі користувача. */
export function applyTheme() {
  const p = WebApp.themeParams || {}
  const root = document.documentElement
  const map = {
    '--tg-bg': p.bg_color,
    '--tg-secondary-bg': p.secondary_bg_color,
    '--tg-text': p.text_color,
    '--tg-hint': p.hint_color,
    '--tg-link': p.link_color,
    '--tg-button': p.button_color,
    '--tg-button-text': p.button_text_color,
    '--tg-destructive': p.destructive_text_color,
  }
  for (const [key, value] of Object.entries(map)) {
    if (value) root.style.setProperty(key, value)
  }
  root.dataset.scheme = WebApp.colorScheme || 'light'
}

export function initTelegram() {
  WebApp.ready()
  WebApp.expand()
  applyTheme()
  WebApp.onEvent('themeChanged', applyTheme)
}

/** Головна дія екрана — нативна MainButton Telegram, а не кнопка в макеті. */
export function useMainButtonApi() {
  return {
    show(text, onClick, { loading = false } = {}) {
      const mb = WebApp.MainButton
      mb.setText(text)
      if (mb._nkHandler) mb.offClick(mb._nkHandler)
      mb._nkHandler = onClick
      mb.onClick(onClick)
      loading ? mb.showProgress(false) : mb.hideProgress()
      mb.show()
    },
    hide() {
      const mb = WebApp.MainButton
      if (mb._nkHandler) mb.offClick(mb._nkHandler)
      mb._nkHandler = null
      mb.hideProgress()
      mb.hide()
    },
  }
}

export function haptic(type = 'light') {
  try { WebApp.HapticFeedback.impactOccurred(type) } catch { /* поза Telegram */ }
}

export function notify(type = 'success') {
  try { WebApp.HapticFeedback.notificationOccurred(type) } catch { /* поза Telegram */ }
}
