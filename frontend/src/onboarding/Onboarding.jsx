import { useState } from 'react'
import Icon from '../components/Icon'

/**
 * Онбординг у два тапи — і обидва можна пропустити.
 *
 * Це не суперечить принципу «без опитувань»: пропуск дорівнює робочому
 * дефолту (режим «автопілот», поріг 5%). Немає жодного екрана, без якого
 * застосунок не працює.
 *
 * Вік і стать не питаємо — вони вже є в silpo_get_my_profile. Питати те,
 * що система знає, — найшвидший спосіб втратити людину на онбордингу.
 */
export default function Onboarding({ settings, name, onDone }) {
  const [step, setStep] = useState(0)
  const [mode, setMode] = useState('auto')
  const [tolKey, setTolKey] = useState('low')

  const modes = settings?.options?.modes || []
  const prices = settings?.options?.price_tolerance || []

  function finish(values = {}) {
    const chosen = prices.find((o) => o.key === tolKey)
    const payload = { mode, onboarded: true, ...values }
    if (!('price_tolerance' in payload) && !('unlimited_price' in payload)) {
      if (chosen && chosen.value === null) payload.unlimited_price = true
      else payload.price_tolerance = chosen?.value ?? 0.05
    }
    onDone(payload)
  }

  if (step === 0) {
    return (
      <div className="screen">
        <div className="body fade" style={{ justifyContent: 'center' }}>
          <div style={{ color: 'var(--brand-text)' }}><Icon name="basket" size={48} /></div>
          <h1>
            {name ? `${name}, ваші чеки ` : 'Ваші чеки '}
            <span className="hl">уже все знають</span>
          </h1>
          <p className="lede">
            Ми не будемо ламати ваш спосіб харчування і вмовляти пити воду замість коли.
            Беремо те, що ви й так купуєте, і шукаємо, де це дешевше або трохи краще.
          </p>
          <p className="muted">
            М'яка оптимізація без ламання лайфстайлу. Рішення завжди за вами.
          </p>
        </div>
        <div className="bottom">
          <button className="btn" onClick={() => setStep(1)}>Далі</button>
          <button className="btn ghost" style={{ marginTop: 8 }} onClick={() => finish()}>
            Пропустити — просто оптимізуй за мене
          </button>
        </div>
      </div>
    )
  }

  if (step === 1) {
    return (
      <div className="screen">
        <div className="body fade">
          <div>
            <h1>Чому ви тут?</h1>
            <p className="lede">Це лише про те, що показувати першим. Змінити можна будь-коли.</p>
          </div>
          <div className="opt-list">
            {modes.map((m) => (
              <button key={m.key} className="opt" aria-pressed={mode === m.key}
                      onClick={() => setMode(m.key)}>
                <span className="dot" aria-hidden="true" />
                <span>
                  <span className="ot">{m.label}</span>
                  <span className="oh">{m.hint}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="bottom">
          <button className="btn" onClick={() => setStep(2)}>Далі</button>
        </div>
      </div>
    )
  }

  const chosen = prices.find((o) => o.key === tolKey)
  const example = chosen && chosen.value != null ? Math.round(100 * (1 + chosen.value)) : null

  return (
    <div className="screen">
      <div className="body fade">
        <div>
          <h1>Скільки можна переплатити?</h1>
          <p className="lede">
            Наскільки дорожчою може бути заміна, яку ми запропонуємо.
          </p>
        </div>
        <div className="opt-list">
          {prices.map((o) => (
            <button key={o.key} className="opt" aria-pressed={tolKey === o.key}
                    onClick={() => setTolKey(o.key)}>
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
            ? <>Для товару за <b>100 ₴</b> покажемо заміни до <b>{example} ₴</b>.</>
            : <>Ціна не фільтруватиме пропозиції.</>}
        </div>
      </div>
      <div className="bottom">
        <button className="btn" onClick={() => finish()}>Готово</button>
      </div>
    </div>
  )
}
