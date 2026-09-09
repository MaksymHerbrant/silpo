import { WebApp } from '../lib/telegram'

export default function Allergens({ data }) {
  const warnings = data?.warnings || []
  const restrictions = data?.restrictions || []
  const hasProfile = restrictions.length > 0

  return (
    <div className="screen fade">
      <div className="card--flat">
        <h1>Обмеження й алергени</h1>
        <p className="muted">Звіряємо склад товарів кошика з вашим профілем Сільпо.</p>
      </div>

      <div className="card">
        <div className="section-title"><h2>Ваш профіль</h2></div>
        {hasProfile ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {restrictions.map((r) => <span className="pill bad" key={r}>🚫 {r}</span>)}
          </div>
        ) : (
          <>
            <p className="muted">
              У профілі Сільпо не вказано жодного обмеження. Заповніть анкету в застосунку
              Сільпо — і ми автоматично перевірятимемо кожен товар кошика.
            </p>
            <button className="btn ghost" style={{ marginTop: 14 }}
                    onClick={() => WebApp.openLink('https://silpo.ua/profile')}>
              Відкрити профіль Сільпо
            </button>
          </>
        )}
      </div>

      <div className="card">
        <div className="section-title">
          <h2>Знайдено в кошику</h2>
          {warnings.length > 0 && <span className="pill bad">{warnings.length}</span>}
        </div>
        {warnings.length === 0 ? (
          <p className="muted">
            {hasProfile
              ? 'Конфліктів зі складом товарів не знайдено.'
              : 'Спершу вкажіть обмеження в профілі Сільпо.'}
          </p>
        ) : (
          warnings.map((w, idx) => (
            <div className="warn-box" key={`${w.product_id}-${idx}`}>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{w.product_title}</div>
              <div className="muted" style={{ marginTop: 4 }}>
                <b>{w.restriction}</b>
                {w.severity === 'high' ? ' — у переліку алергенів: ' : ' — у складі: '}
                …{w.matched_text}…
              </div>
            </div>
          ))
        )}
        <p className="muted" style={{ marginTop: 10 }}>
          Перевірка робиться за атрибутами «Містить алергени» та «Склад» із каталогу Сільпо
          і не замінює читання етикетки.
        </p>
      </div>
    </div>
  )
}
