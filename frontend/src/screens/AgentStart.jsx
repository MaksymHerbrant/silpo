import Screen from '../components/Screen'

/**
 * Стартовий екран. Показує лише факти з чеків — жодних вигаданих обіцянок.
 * Потенційну економію не малюємо: реальна відома тільки після збірки.
 */
export default function AgentStart({ context, goalLabel, onRun, running }) {
  const stats = context?.stats
  return (
    <Screen
      title="Агент"
      action={
        <button className="btn" onClick={onRun} disabled={running}>
          {running ? 'Агент працює…' : 'Запустити агента'}
        </button>
      }
    >
      <h1>
        Ти не складаєш кошик.<br />
        <span className="hl">Твій агент</span> робить це за тебе.
      </h1>

      {stats ? (
        <>
          <p className="lede">
            Проаналізовано {stats.period_days} днів покупок і {stats.receipts} чеків.
            Агент готовий зібрати кошик під твою мету — {goalLabel?.toLowerCase()}.
          </p>
          <div className="card">
            {stats.top_category && (
              <div className="row" style={{ borderTop: 'none', marginTop: 0, paddingTop: 0 }}>
                <span className="k">{stats.top_category.label} у покупках</span>
                <span className="v">{stats.top_category.share}%</span>
              </div>
            )}
            <div className="row">
              <span className="k">Витрачено за {stats.period_days} днів</span>
              <span className="v">{Math.round(stats.total_spend).toLocaleString('uk-UA')} ₴</span>
            </div>
            <div className="row">
              <span className="k">Зекономлено на акціях</span>
              <span className="v money">{Math.round(stats.saved).toLocaleString('uk-UA')} ₴</span>
            </div>
          </div>
          <p className="muted">
            Агент використає твою історію покупок, актуальні акції й купони мережі.
          </p>
        </>
      ) : (
        <p className="lede">
          Агент прочитає твою історію покупок у Сільпо, знайде акції й збере кошик
          під твою мету та бюджет.
        </p>
      )}
    </Screen>
  )
}
