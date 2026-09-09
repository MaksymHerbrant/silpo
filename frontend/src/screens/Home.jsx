import MacroDonut from '../components/MacroDonut'
import MacroNorms from '../components/MacroNorms'
import ScoreRing from '../components/ScoreRing'

function badgeColor(score) {
  return score >= 70 ? 'var(--good)' : score >= 45 ? 'var(--warn)' : 'var(--bad)'
}

const GRADES = {
  A: 'Чудовий баланс', B: 'Хороший баланс', C: 'Можна краще',
  D: 'Розбалансований', E: 'Варто переглянути',
}

export default function Home({ analysis, onRefresh, onSendReport, sending }) {
  if (analysis?.empty) {
    return (
      <div className="screen">
        <div className="card center">
          <div style={{ fontSize: 40, marginBottom: 10 }}>🛒</div>
          <h2 style={{ marginBottom: 6 }}>Кошик порожній</h2>
          <p className="muted">{analysis.reason}</p>
          <button className="btn ghost" style={{ marginTop: 18 }} onClick={onRefresh}>
            Оновити
          </button>
        </div>
      </div>
    )
  }

  const items = [...(analysis.items || [])].sort((a, b) => (a.score ?? 999) - (b.score ?? 999))
  const totals = analysis.totals || {}
  const worst = items.find((i) => i.score !== null)

  return (
    <div className="screen fade">
      <div className="hero">
        <div className="hero-top">
          <ScoreRing score={analysis.score} letter={analysis.letter} />
          <div className="hero-text">
            <div className="grade">{GRADES[analysis.letter] || 'Оцінка кошика'}</div>
            <p className="muted" style={{ marginTop: 4 }}>
              {analysis.items.length} товар(ів) · {Math.round(totals.mass_g || 0)} г ·{' '}
              {Math.round(totals.price || 0)} грн
            </p>
          </div>
        </div>
        {analysis.summary_text && (
          <p className="muted" style={{ marginTop: 14, fontSize: 13.5, lineHeight: 1.5 }}>
            {analysis.summary_text}
          </p>
        )}
      </div>

      <div className="card">
        <div className="section-title">
          <h2>Звідки калорії</h2>
          <span className="muted">{analysis.energy_density} ккал/100 г</span>
        </div>
        <MacroDonut shares={analysis.shares} totals={totals} />
      </div>

      <div className="card">
        <div className="section-title">
          <h2>Баланс проти норми</h2>
        </div>
        <MacroNorms shares={analysis.shares} deviations={analysis.deviations} />
      </div>

      {worst && (
        <div className="card">
          <div className="section-title">
            <h2>Товари</h2>
            <span className="muted">{analysis.coverage?.pct}% з даними</span>
          </div>
          {items.map((i) => (
            <div className="item" key={i.slug || i.product_id}>
              {i.image
                ? <img src={i.image} alt="" loading="lazy" />
                : <div className="item-img-placeholder" style={{
                    width: 44, height: 44, borderRadius: 10, background: 'var(--tg-secondary-bg)',
                  }} />}
              <div className="item-body">
                <div className="item-title">{i.title}</div>
                <div className="item-sub">
                  {i.note
                    || [
                      i.grams ? `${Math.round(i.grams)} г` : null,
                      i.nutrition?.energy_kcal ? `${i.nutrition.energy_kcal} ккал/100 г` : null,
                      i.is_own_brand ? 'власна марка' : null,
                    ].filter(Boolean).join(' · ')}
                </div>
              </div>
              <span className={`badge${i.score === null ? ' na' : ''}`}
                    style={i.score === null ? undefined : { background: badgeColor(i.score) }}>
                {i.score === null ? 'н/д' : i.score}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3 style={{ marginBottom: 8 }}>Як рахується оцінка</h3>
        <p className="muted">{analysis.methodology}</p>
        {analysis.coverage?.skipped > 0 && (
          <p className="muted" style={{ marginTop: 8 }}>
            {analysis.coverage.skipped} товар(ів) без харчової цінності не враховано — ми не
            підставляємо нулі замість відсутніх даних.
          </p>
        )}
        <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
          <button className="btn ghost" onClick={onRefresh}>Перерахувати</button>
          <button className="btn" onClick={onSendReport} disabled={sending}>
            {sending ? 'Надсилаю…' : 'Звіт у чат'}
          </button>
        </div>
      </div>
    </div>
  )
}
