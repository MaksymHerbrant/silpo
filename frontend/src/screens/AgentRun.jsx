import Screen from '../components/Screen'

/**
 * Живий трейс: кроки з'являються по мірі виконання, бекенд віддає їх
 * у /agent/run поки building=true. Внутрішніх міркувань моделі тут немає —
 * лише дії, які вона виконала.
 */
export default function AgentRun({ steps, building, error, onOpenBasket, onBack }) {
  const done = !building && !error

  return (
    <Screen
      title="Виконання"
      onBack={onBack}
      action={
        <button className="btn" onClick={onOpenBasket} disabled={!done}>
          {building ? 'Агент працює…' : 'Переглянути кошик'}
        </button>
      }
    >
      <div>
        <h1>Агент працює</h1>
        <p className="lede">Без зайвих деталей — лише те, що він знайшов і чому.</p>
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '3px solid var(--danger)' }}>
          <h3>Не вдалось завершити</h3>
          <p className="muted" style={{ marginTop: 6 }}>{error}</p>
        </div>
      )}

      <div className="trace">
        {steps.map((s, i) => (
          <div className="trace-item" key={`${s.tool}-${i}`}>
            <span className="check">✓</span>
            <div>
              <div className="t">{s.title}</div>
              {s.subtitle && <div className="s">{s.subtitle}</div>}
            </div>
          </div>
        ))}
        {building && (
          <div className="trace-item">
            <span className="check pending">•</span>
            <div>
              <div className="t" style={{ color: 'var(--ink-3)' }}>
                {steps.length ? 'Наступний крок…' : 'Читаю ваш профіль…'}
              </div>
            </div>
          </div>
        )}
      </div>
    </Screen>
  )
}
