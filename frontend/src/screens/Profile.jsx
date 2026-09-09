import CategoryChart from '../components/CategoryChart'
import MacroDonut from '../components/MacroDonut'
import MacroNorms from '../components/MacroNorms'
import ScoreRing from '../components/ScoreRing'
import TrendChart from '../components/TrendChart'

const GRADES = {
  A: 'Збалансований раціон', B: 'Хороший раціон', C: 'Є що покращити',
  D: 'Розбалансований раціон', E: 'Варто переглянути звички',
}

function badgeColor(score) {
  return score >= 70 ? 'var(--good)' : score >= 45 ? 'var(--warn)' : 'var(--bad)'
}

/**
 * Головний екран — Нутрі-профіль за реальними чеками Сільпо.
 * Кошик тут другорядний: він майже завжди порожній, а чеки за три місяці
 * показують справжню картину харчування.
 */
export default function Profile({
  trend, cart, loading, onRefresh, onOpenCart, onSendReport, sending,
}) {
  const profile = trend?.profile
  const habits = trend?.habits
  const summary = habits?.summary
  const weeks = trend?.weeks || []
  const delta = trend?.delta_vs_prev_week

  if (loading || trend?.building) {
    return (
      <div className="center">
        <div className="spinner" />
        Аналізуємо ваші чеки…
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          Це займає до хвилини: читаємо чеки й харчову цінність кожного товару
        </div>
      </div>
    )
  }

  // Тижні є, а звичок ще нема (кеш злетів) — показуємо тренд і кнопку добудови
  if (!summary && weeks.length > 0) {
    return (
      <div className="screen fade">
        <div className="card">
          <div className="section-title"><h2>Оцінка по тижнях</h2></div>
          <TrendChart weeks={weeks} />
          <button className="btn" style={{ marginTop: 14 }} onClick={onRefresh}>
            Порахувати повний профіль
          </button>
        </div>
      </div>
    )
  }

  if (!summary) {
    return (
      <div className="screen">
        <div className="card center">
          <div style={{ fontSize: 40, marginBottom: 10 }}>🧾</div>
          <h2 style={{ marginBottom: 6 }}>Чеків поки не знайшли</h2>
          <p className="muted">
            {trend?.reason
              || 'Ми аналізуємо покупки з ваших чеків Сільпо. Зробіть покупку — і профіль зʼявиться.'}
          </p>
          <button className="btn ghost" style={{ marginTop: 18 }} onClick={onRefresh}>Оновити</button>
        </div>
      </div>
    )
  }

  const cartItems = cart && !cart.empty ? cart.items?.length : 0

  return (
    <div className="screen fade">
      <div className="hero">
        <div className="hero-top">
          <ScoreRing score={profile?.score} letter={profile?.letter} />
          <div className="hero-text">
            <div className="grade">{GRADES[profile?.letter] || 'Ваш нутрі-профіль'}</div>
            <p className="muted" style={{ marginTop: 4 }}>
              {summary.orders_count} чеків за {summary.period_days} днів ·{' '}
              {summary.visits_per_week} візити на тиждень
            </p>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 14, fontSize: 13.5, lineHeight: 1.5 }}>
          Оцінка рахується за всіма товарами з ваших чеків, а не за одним кошиком —
          так видно реальні звички, а не разову покупку.
        </p>
      </div>

      {cartItems > 0 && (
        <div className="card" onClick={onOpenCart} style={{ cursor: 'pointer' }}>
          <div className="row">
            <div>
              <h3>Зараз у кошику</h3>
              <p className="muted" style={{ marginTop: 3 }}>
                {cartItems} товар(ів) · перевірити перед покупкою →
              </p>
            </div>
            <span className="badge" style={{ background: badgeColor(cart.score) }}>{cart.score}</span>
          </div>
        </div>
      )}

      <div className="stats">
        <div className="stat">
          <div className="n">{summary.avg_check} ₴</div>
          <div className="t">середній чек</div>
        </div>
        <div className="stat">
          <div className="n">{Math.round(summary.total_spend)} ₴</div>
          <div className="t">витрачено за {summary.period_days} днів</div>
        </div>
        <div className="stat">
          <div className="n" style={{ color: 'var(--good)' }}>
            {Math.round(summary.total_saved)} ₴
          </div>
          <div className="t">зекономлено на акціях</div>
        </div>
        <div className="stat">
          <div className="n">{summary.visits_per_week}</div>
          <div className="t">візити на тиждень</div>
        </div>
      </div>

      {profile && (
        <>
          <div className="card">
            <div className="section-title">
              <h2>Звідки калорії</h2>
              <span className="muted">{profile.energy_density} ккал/100 г</span>
            </div>
            <MacroDonut shares={profile.shares} totals={profile.totals} />
          </div>

          <div className="card">
            <div className="section-title"><h2>Баланс проти норми ВООЗ</h2></div>
            <MacroNorms shares={profile.shares} deviations={profile.deviations} />
          </div>
        </>
      )}

      <div className="card">
        <div className="section-title">
          <h2>Оцінка по тижнях</h2>
          {delta != null && (
            <span className={`pill ${delta >= 0 ? 'good' : 'bad'}`}>
              {delta >= 0 ? '↑' : '↓'} {Math.abs(delta)}
            </span>
          )}
        </div>
        {weeks.length > 1
          ? <TrendChart weeks={weeks} />
          : <p className="muted">Замало тижнів із даними, щоб малювати тренд.</p>}
      </div>

      {habits?.categories?.length > 0 && (
        <div className="card">
          <div className="section-title">
            <h2>На що йдуть гроші</h2>
            <span className="muted">{summary.favourite_branch}</span>
          </div>
          <CategoryChart categories={habits.categories} />
        </div>
      )}

      {habits?.top_products?.length > 0 && (
        <div className="card">
          <div className="section-title">
            <h2>Купуєте найчастіше</h2>
            <span className="muted">за {summary.orders_count} чеків</span>
          </div>
          {habits.top_products.map((p) => (
            <div className="item" key={p.slug}>
              {p.image
                ? <img src={p.image} alt="" loading="lazy" />
                : <div style={{ width: 44, height: 44, borderRadius: 10, background: 'var(--tg-secondary-bg)' }} />}
              <div className="item-body">
                <div className="item-title">{p.title}</div>
                <div className="item-sub">{Math.round(p.times)} раз(и) за період</div>
              </div>
              {p.score != null && (
                <span className="badge" style={{ background: badgeColor(p.score) }}>{p.score}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3 style={{ marginBottom: 8 }}>Як рахується оцінка</h3>
        <p className="muted">{profile?.methodology}</p>
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
