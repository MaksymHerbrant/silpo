import { useState } from 'react'
import Screen from '../components/Screen'

/**
 * Налаштування агента.
 *
 * Ціновий поріг стоїть ПЕРШИМ і навмисно: за опитуванням ціна — критерій
 * вибору №1 (62%), а готовність переплачувати низька. Це не другорядна
 * галочка, а головний регулятор того, що взагалі потрапляє в пропозиції.
 */
export default function Settings({ settings, restrictions = [], busy, onSave, onLogout,
                                   onOpenLive, onOpenNutrition }) {
  const priceOptions = settings?.options?.price_tolerance || []
  const modes = settings?.options?.modes || []

  const [tolKey, setTolKey] = useState(settings?.price_tolerance_key || 'low')
  const [mode, setMode] = useState(settings?.mode || 'auto')

  const dirty = tolKey !== settings?.price_tolerance_key || mode !== settings?.mode
  const current = priceOptions.find((o) => o.key === tolKey)
  // Наочно: що поріг означає для товару за круглі 100 ₴
  const example = current && current.value != null
    ? Math.round(100 * (1 + current.value))
    : null

  function save() {
    const payload = { mode }
    if (current && current.value === null) payload.unlimited_price = true
    else payload.price_tolerance = current?.value ?? 0.05
    onSave(payload)
  }

  return (
    <Screen
      title="Налаштування"
      tabs
      action={
        <button className="btn" onClick={save} disabled={!dirty || busy}>
          {busy ? 'Перебудовуємо план…' : dirty ? 'Зберегти і перебудувати план' : 'Збережено'}
        </button>
      }
    >
      <section className="section">
        <div>
          <h3>Ціновий поріг</h3>
          <p className="muted" style={{ marginTop: 4 }}>
            Наскільки дорожчою може бути запропонована заміна.
          </p>
        </div>

        <div className="opt-list">
          {priceOptions.map((o) => (
            <button
              className="opt"
              key={o.key}
              aria-pressed={tolKey === o.key}
              onClick={() => setTolKey(o.key)}
            >
              <span className="dot" aria-hidden="true" />
              <span>
                <span className="ot">{o.label}</span>
                <span className="oh">{o.hint}</span>
              </span>
            </button>
          ))}
        </div>

        <div className="effect">
          {example
            ? <>Для товару за <b>100 ₴</b> покажемо заміни до <b>{example} ₴</b>. Дорожчі
                сховаємо під «показати ще варіанти» — самі їх не підставимо.</>
            : <>Ціна не фільтрує пропозиції. Ми все одно ставимо дешевші варіанти першими.</>}
        </div>
      </section>

      <section className="section">
        <div>
          <h3>Режим</h3>
          <p className="muted" style={{ marginTop: 4 }}>
            Що агент виносить угору. Рахує він завжди все однаково.
          </p>
        </div>
        {settings?.mode_note && (
          <div className="effect">Зараз: {settings.mode_note}</div>
        )}
        <div className="opt-list">
          {modes.map((m) => (
            <button
              className="opt"
              key={m.key}
              aria-pressed={mode === m.key}
              onClick={() => setMode(m.key)}
            >
              <span className="dot" aria-hidden="true" />
              <span>
                <span className="ot">{m.label}</span>
                <span className="oh">{m.hint}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="section">
        <div>
          <h3>Обмеження</h3>
          <p className="muted" style={{ marginTop: 4 }}>
            Беруться з анкети в застосунку Сільпо. Ми їх не вигадуємо.
          </p>
        </div>

        {restrictions.length === 0 ? (
          <div className="card plain">
            <p className="muted">
              У профілі Сільпо обмежень не вказано. Заповніть анкету в застосунку —
              і ми перевірятимемо склад кожного товару.
            </p>
          </div>
        ) : (
          <div className="card plain">
            {restrictions.map((r) => (
              <div className="kv" key={r.slug}>
                <span className="k">{r.label}</span>
                <span className="v">
                  {r.kind === 'allergen'
                    ? <span className="tag warn">🔒 жорсткий блок</span>
                    : <span className="tag good">м'яка заміна</span>}
                </span>
              </div>
            ))}
            <p className="over-note">
              Алерген блокує завжди — це не налаштовується.
            </p>
          </div>
        )}
      </section>

      <section className="section">
        <button className="link-row" onClick={onOpenNutrition}>
          <span>🥗 Харчування — що варто додати</span>
          <span className="chev">›</span>
        </button>
        <button className="link-row" onClick={onOpenLive}>
          <span>🔌 Живі дані — доказ роботи через MCP</span>
          <span className="chev">›</span>
        </button>
      </section>

      <section className="section">
        <button className="btn danger" onClick={onLogout} disabled={busy}>
          Вийти з акаунта
        </button>
        <p className="over-note">
          Відключаємо доступ до Сільпо і стираємо зібрані дані. Ваш поріг
          і режим лишаються — якщо повернетесь, питати заново не будемо.
        </p>
      </section>
    </Screen>
  )
}
