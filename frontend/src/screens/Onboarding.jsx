import { useState } from 'react'
import { api } from '../lib/api'
import { WebApp } from '../lib/telegram'

export default function Onboarding({ user, onConnected }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function connect() {
    setBusy(true)
    setError(null)
    try {
      const { authorize_url, demo_mode } = await api.silpoStart()
      if (demo_mode) return onConnected()
      // Telegram WebView нестабільно тримає сторонні OAuth-popup'и,
      // тому авторизацію відкриваємо в зовнішньому браузері.
      WebApp.openLink(authorize_url, { try_instant_view: false })
      setError(
        'Заверши вхід у браузері, що відкрився. Після цього Telegram поверне тебе сюди — ' +
          'натисни «Я вже увійшов».',
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="screen">
      <div className="card">
        <h2>Привіт{user?.first_name ? `, ${user.first_name}` : ''} 👋</h2>
        <p className="muted">
          «Нутрі-Кошик» аналізує те, що ти вже купуєш у Сільпо. Нічого вносити руками не треба:
          дані про товари беруться напряму з твого кошика та історії замовлень.
        </p>
      </div>

      <div className="card">
        <h3>Що ти отримаєш</h3>
        <p className="muted">
          • Рейтинг здоров'я кошика 0–100 і клас A–E<br />
          • Розклад БЖУ та доданого цукру<br />
          • Попередження про алергени з твого профілю Сільпо<br />
          • Тижневий тренд і пропозиції здоровіших замін
        </p>
      </div>

      <div className="card">
        <h3>Під'єднай акаунт Сільпо</h3>
        <p className="muted" style={{ marginBottom: 14 }}>
          Авторизація відбувається на боці Сільпо (OAuth 2.1 + PKCE). Токен зберігається лише на
          нашому сервері в зашифрованому вигляді — у застосунку його немає.
        </p>
        <button className="btn" onClick={connect} disabled={busy}>
          {busy ? 'Відкриваю…' : "Під'єднати Сільпо"}
        </button>
        {error && (
          <>
            <p className="muted" style={{ marginTop: 12 }}>{error}</p>
            <button className="btn secondary" style={{ marginTop: 10 }} onClick={onConnected}>
              Я вже увійшов
            </button>
          </>
        )}
      </div>
    </div>
  )
}
