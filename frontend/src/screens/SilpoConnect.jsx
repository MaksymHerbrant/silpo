import { useState } from 'react'
import Screen from '../components/Screen'
import { api } from '../lib/api'
import { WebApp } from '../lib/telegram'

export default function SilpoConnect({ user, onConnected }) {
  const [busy, setBusy] = useState(false)
  const [hint, setHint] = useState(null)

  async function connect() {
    setBusy(true)
    try {
      const { authorize_url, demo_mode } = await api.silpoStart()
      if (demo_mode) return onConnected()
      // WebView Telegram нестабільно тримає сторонні OAuth-вікна,
      // тому авторизацію відкриваємо в зовнішньому браузері.
      WebApp.openLink(authorize_url)
      setHint('Заверши вхід у браузері, що відкрився, і повернись сюди.')
    } catch (e) {
      setHint(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Screen
      title="Підключення"
      action={
        <button className="btn" onClick={hint ? onConnected : connect} disabled={busy}>
          {busy ? 'Відкриваю…' : hint ? 'Я вже увійшов' : "Під'єднати Сільпо"}
        </button>
      }
    >
      <div>
        <h1>Привіт{user?.first_name ? `, ${user.first_name}` : ''}</h1>
        <p className="lede">
          Щоб агент зібрав кошик, йому потрібен доступ до твоєї історії покупок
          і кошика в Сільпо.
        </p>
      </div>
      <div className="card">
        <h3>Що буде далі</h3>
        <p className="muted" style={{ marginTop: 8 }}>
          Вхід відбувається на боці Сільпо. Токен зберігається лише на нашому
          сервері в зашифрованому вигляді — у застосунку його немає.
        </p>
      </div>
      {hint && <p className="muted">{hint}</p>}
    </Screen>
  )
}
