import Screen from '../components/Screen'

/** Аналітика окремим екраном: гроші, категорії, динаміка. Без оцінок. */
export default function Insights({ data, onBack }) {
  if (!data?.has_data) {
    return (
      <Screen title="Мої покупки" onBack={onBack}>
        <div className="center">
          {data ? (data.reason || 'Даних поки немає') : <><div className="spinner" />Рахую…</>}
        </div>
      </Screen>
    )
  }

  const { money, period, top_by_spend: top = [], categories, weeks = [] } = data
  const maxSpend = Math.max(...weeks.map((w) => w.spend), 1)
  const maxItem = Math.max(...top.map((t) => t.spend), 1)

  return (
    <Screen title="Мої покупки" onBack={onBack}>
      <div>
        <h1>За {period.days} днів</h1>
        <p className="lede">{period.receipts} чеків, з {period.first} по {period.last}.</p>
      </div>

      <div className="stat-grid">
        <div className="stat-tile">
          <div className="n">{Math.round(money.per_week).toLocaleString('uk-UA')} ₴</div>
          <div className="t">на тиждень</div>
        </div>
        <div className="stat-tile">
          <div className="n">{Math.round(money.avg_check)} ₴</div>
          <div className="t">середній чек</div>
        </div>
        <div className="stat-tile">
          <div className="n money">{Math.round(money.total_saved).toLocaleString('uk-UA')} ₴</div>
          <div className="t">зекономлено на акціях ({money.saved_share}%)</div>
        </div>
        <div className="stat-tile">
          <div className="n">{money.visits_per_week}</div>
          <div className="t">візити на тиждень</div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 12 }}>Куди йдуть гроші</h3>
        {top.slice(0, 6).map((t) => (
          <div className="bar-item" key={t.name}>
            <div className="bar-head">
              <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {t.name}
              </span>
              <span className="amt">{Math.round(t.spend)} ₴ · {t.share_of_spend}%</span>
            </div>
            <div className="bar-track"><i style={{ width: `${(t.spend / maxItem) * 100}%` }} /></div>
          </div>
        ))}
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 12 }}>За категоріями</h3>
        {(categories?.categories || []).slice(0, 7).map((c) => (
          <div className="bar-item" key={c.key}>
            <div className="bar-head">
              <span>{c.label}</span>
              <span className="amt">{c.share}% · {Math.round(c.spend)} ₴</span>
            </div>
            <div className="bar-track">
              <i className={c.status === 'above' ? 'warn' : ''} style={{ width: `${Math.min(c.share, 100)}%` }} />
            </div>
          </div>
        ))}
        <p className="muted" style={{ marginTop: 10 }}>{categories?.methodology}</p>
      </div>

      {weeks.length > 1 && (
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>Витрати по тижнях</h3>
          <div className="spark">
            {weeks.map((w) => (
              <div key={w.week} title={`${w.week}: ${Math.round(w.spend)} ₴`}>
                <i style={{ height: `${(w.spend / maxSpend) * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="spark-labels">
            {weeks.map((w) => <span key={w.week}>{w.week.slice(8)}.{w.week.slice(5, 7)}</span>)}
          </div>
        </div>
      )}
    </Screen>
  )
}
