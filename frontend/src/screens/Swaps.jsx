import { useEffect } from 'react'
import { haptic, useMainButtonApi } from '../lib/telegram'

/**
 * Своп-пропозиції. Головна дія — нативна MainButton Telegram,
 * а не кнопка в макеті: так вимагає UX Mini App.
 */
export default function Swaps({ swaps, stats, selected, onSelect, onApply, onDecline, applying }) {
  const mainButton = useMainButtonApi()

  useEffect(() => {
    const swap = swaps.find((s) => s.id === selected)
    if (!swap) {
      mainButton.hide()
      return undefined
    }
    mainButton.show(
      applying ? 'Застосовуємо…' : `Замінити на «${swap.suggested_title}»`,
      () => onApply(swap.id),
      { loading: applying },
    )
    return () => mainButton.hide()
  }, [selected, swaps, applying])

  if (!swaps.length) {
    return (
      <div className="screen">
        <div className="card center">
          <div style={{ fontSize: 40, marginBottom: 10 }}>🎉</div>
          <h2 style={{ marginBottom: 6 }}>Замін не потрібно</h2>
          <p className="muted">
            Ми не знайшли товарів, які варто замінити: або кошик уже збалансований, або в
            аналогів немає даних про харчову цінність.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="screen fade">
      <div className="card--flat">
        <h1>Розумні заміни</h1>
        <p className="muted">
          Пропозиції побудовані на ваших чеках: беремо те, що ви купуєте регулярно,
          і шукаємо здоровішу альтернативу в Сільпо. Є активний кошик — міняємо в ньому,
          немає — додаємо в обране.
        </p>
        {stats?.acceptance_rate != null && (
          <p className="muted" style={{ marginTop: 6 }}>
            Прийнято замін: {stats.accepted} з {stats.decided} ({stats.acceptance_rate}%)
          </p>
        )}
      </div>

      {swaps.map((s) => {
        const active = s.id === selected
        const priceDelta =
          s.suggested_price && s.original_price
            ? Math.round((s.suggested_price - s.original_price) * 100) / 100
            : null
        return (
          <div
            key={s.id}
            className="card"
            onClick={() => { haptic(); onSelect(active ? null : s.id) }}
            style={{ outline: active ? '2px solid var(--tg-link)' : 'none', cursor: 'pointer' }}
          >
            {s.problem && (
              <div className="muted" style={{ marginBottom: 10, fontSize: 12 }}>
                {s.problem}
                {s.times_bought > 1 && ` · купуєте ${Math.round(s.times_bought)} раз(и)`}
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {s.original_image && (
                <img src={s.original_image} alt="" loading="lazy"
                     style={{ width: 40, height: 40, borderRadius: 9, objectFit: 'contain',
                              background: 'var(--tg-secondary-bg)', opacity: .55 }} />
              )}
              <span style={{ color: 'var(--tg-hint)' }}>→</span>
              {s.suggested_image && (
                <img src={s.suggested_image} alt="" loading="lazy"
                     style={{ width: 48, height: 48, borderRadius: 10, objectFit: 'contain',
                              background: 'var(--tg-secondary-bg)' }} />
              )}
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="item-sub" style={{ textDecoration: 'line-through' }}>
                  {s.original_title}
                </div>
                <div style={{ fontWeight: 620, marginTop: 3, fontSize: 14 }}>
                  {s.suggested_title}
                </div>
              </div>
              <span className="badge" style={{ background: 'var(--good)' }}>
                +{Math.round(s.score_delta)}
              </span>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '12px 0 10px' }}>
              <span className="pill">{s.original_score} → {s.suggested_score} балів</span>
              {s.is_own_brand && <span className="pill good">власна марка Сільпо</span>}
              {s.on_promotion && <span className="pill warn">зараз в акції</span>}
              {s.in_cart && <span className="pill">у кошику</span>}
              {priceDelta !== null && (
                <span className={`pill ${priceDelta <= 0 ? 'good' : ''}`}>
                  {priceDelta > 0 ? `+${priceDelta}` : priceDelta} ₴
                </span>
              )}
            </div>

            <p className="muted">{s.reason}</p>
            <button className="btn ghost" style={{ marginTop: 12 }}
                    onClick={(e) => { e.stopPropagation(); onDecline(s.id) }}>
              Не цікавить
            </button>
          </div>
        )
      })}
    </div>
  )
}
