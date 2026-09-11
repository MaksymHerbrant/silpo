import { useState } from 'react'
import Sheet from '../components/Sheet'

/** Глибока деталізація однієї позиції: історія, склад, алергени, акція. */
export default function ItemDetail({ item, onClose, onSwitch, chosen, onOpenSettings }) {
  const [showOver, setShowOver] = useState(false)
  if (!item) return null
  const d = item.detail || {}
  const alt = item.alternative
  const useAlt = chosen?.useAlternative
  const over = item.alternatives_over || []

  return (
    <Sheet title={item.name} onClose={onClose}>
      {item.image && (
        <img src={item.image} alt="" style={{
          width: 96, height: 96, objectFit: 'contain', borderRadius: 14,
          background: 'var(--surface)', alignSelf: 'center',
        }} />
      )}

      {(() => {
        const hits = item.allergen_hits || []
        const blocking = hits.filter((h) => h.action === 'block')
        const swaps = hits.filter((h) => h.action === 'swap')
        const infos = hits.filter((h) => h.action === 'info')
        const tone = blocking.length ? 'bad' : 'ok'
        return (
          <div className={`verdict ${tone}`}>
            <b>{blocking.length ? '⛔ ' : swaps.length ? '🎯 ' : '✓ '}</b>
            {blocking.length
              ? 'У складі знайдено ваш алерген'
              : swaps.length
                ? 'Є чистіший варіант під ваше вподобання'
                : d.allergen_check}
            {blocking.map((h, i) => (
              <div key={`b${i}`} style={{ marginTop: 6 }}>
                <b>{h.restriction}</b> — у складі: …{h.matched}…
              </div>
            ))}
            {swaps.map((h, i) => (
              <div key={`s${i}`} style={{ marginTop: 6 }}>
                <b>{h.restriction}</b> — у профілі вказано уникати в цій категорії
              </div>
            ))}
            {infos.length > 0 && (
              <div style={{ marginTop: 6, opacity: .75 }}>
                {infos.map((h) => h.restriction).join(', ')} — присутнє як технологічний
                компонент, не блокуємо
              </div>
            )}
          </div>
        )
      })()}

      {(item.evidence || []).length > 0 && (
        <div className="card plain">
          <h3 style={{ marginBottom: 8 }}>Чому я це пропоную</h3>
          <p className="muted" style={{ marginBottom: 10 }}>
            Підстави, які можна перевірити — не міркування моделі.
          </p>
          {item.evidence.map((e, n) => (
            <div className="kv" key={n}>
              <span className="k">{e.label}</span>
              <span className="v">{e.value} {e.unit}</span>
            </div>
          ))}
        </div>
      )}

      <div className="card plain">
        <h3 style={{ marginBottom: 8 }}>Чому в кошику</h3>
        {item.kind_note && <p className="muted" style={{ marginBottom: 8 }}>{item.kind_note}</p>}
        {item.kind_key && (
          <>
            <div className="kv">
              <span className="k">Вид товару</span>
              <span className="v">{item.kind_key}</span>
            </div>
            <div className="kv">
              <span className="k">Різних марок брали</span>
              <span className="v">{item.kind_brands}</span>
            </div>
            <div className="kv">
              <span className="k">Вірність марці</span>
              <span className="v">
                {item.brand_indifferent ? 'марка не принципова' : `${Math.round((item.loyalty || 0) * 100)}%`}
              </span>
            </div>
          </>
        )}
        {item.habit && (
          <>
            <div className="kv">
              <span className="k">Тип покупки</span>
              <span className="v">{item.habit.label}</span>
            </div>
            <div className="kv">
              <span className="k">Різних днів покупки</span>
              <span className="v">{item.habit.days}</span>
            </div>
            <div className="kv">
              <span className="k">Різних тижнів</span>
              <span className="v">{item.habit.weeks}</span>
            </div>
            {item.habit.since_last_days != null && (
              <div className="kv">
                <span className="k">Востаннє</span>
                <span className="v">{item.habit.since_last_days} дн. тому</span>
              </div>
            )}
          </>
        )}
        <p className="muted" style={{ marginTop: 8 }}>{d.why}</p>
        {item.agent_why && (
          <p className="muted" style={{ marginTop: 6 }}>🤖 {item.agent_why}</p>
        )}
        {item.alternative_rejected && (
          <p className="over-note">
            🤖 Агент відхилив заміну «{item.alternative_rejected.name}»:
            {' '}{item.alternative_rejected.why}
          </p>
        )}
        {item.note && <p className="muted" style={{ marginTop: 6 }}>{item.note}</p>}
      </div>

      <div className="card plain">
        <h3 style={{ marginBottom: 6 }}>Цифри</h3>
        <div className="kv"><span className="k">Ціна зараз</span><span className="v">{item.price} ₴</span></div>
        {item.on_promotion && (
          <div className="kv">
            <span className="k">Було</span>
            <span className="v">{item.old_price} ₴ <b className="money">−{Math.round(item.saved)} ₴</b></span>
          </div>
        )}
        <div className="kv"><span className="k">Купували разів</span><span className="v">{d.times_bought}</span></div>
        <div className="kv"><span className="k">Витрачено всього</span><span className="v">{d.total_spend} ₴</span></div>
        <div className="kv"><span className="k">Середня ціна</span><span className="v">{d.avg_price} ₴</span></div>
        {d.brand && <div className="kv"><span className="k">Марка</span><span className="v">{d.brand}</span></div>}
        {d.country && <div className="kv"><span className="k">Країна</span><span className="v">{d.country}</span></div>}
      </div>

      {d.nutrition?.kcal != null && (
        <div className="card plain">
          <h3 style={{ marginBottom: 6 }}>Харчова цінність на 100 г</h3>
          <div className="kv"><span className="k">Калорійність</span><span className="v">{d.nutrition.kcal} ккал</span></div>
          {d.nutrition.protein != null && <div className="kv"><span className="k">Білки</span><span className="v">{d.nutrition.protein} г</span></div>}
          {d.nutrition.fat != null && <div className="kv"><span className="k">Жири</span><span className="v">{d.nutrition.fat} г</span></div>}
          {d.nutrition.carbs != null && <div className="kv"><span className="k">Вуглеводи</span><span className="v">{d.nutrition.carbs} г</span></div>}
        </div>
      )}

      {(d.allergens_text || d.ingredients) && (
        <div className="card plain">
          <h3 style={{ marginBottom: 8 }}>Склад</h3>
          {d.allergens_text && <p className="muted"><b>Містить алергени:</b> {d.allergens_text}</p>}
          {d.ingredients && <p className="muted" style={{ marginTop: 6 }}>{d.ingredients}</p>}
        </div>
      )}

      {(item.members || []).length > 1 && (
        <div className="card plain">
          <h3 style={{ marginBottom: 8 }}>Які марки ви брали</h3>
          {item.members.map((m) => (
            <div className="hist-row" key={m.slug}>
              <span>{m.name}</span>
              <span className="d">{m.days} дн. · {Math.round(m.spend)} ₴</span>
            </div>
          ))}
        </div>
      )}

      {d.history?.length > 0 && (
        <div className="card plain">
          <h3 style={{ marginBottom: 8 }}>Історія покупок</h3>
          {d.history.map((h, i) => (
            <div className="hist-row" key={i}>
              <span className="d">{h.date}</span>
              <span>{h.quantity} × {h.price} ₴</span>
            </div>
          ))}
        </div>
      )}

      {alt && (
        <div className="card plain">
          <h3 style={{ marginBottom: 8 }}>Знайдена альтернатива</h3>
          <div className="kv"><span className="k">{alt.name}</span><span className="v">{alt.price} ₴</span></div>
          <p className="muted" style={{ marginTop: 6 }}>{alt.why}
            {alt.saved > 0 && <b className="money"> · економія {Math.round(alt.saved)} ₴</b>}
          </p>
          {alt.composition_known === false && (
            <p className="over-note" style={{ color: 'var(--money)', fontWeight: 600 }}>
              ⚠️ Каталог не публікує склад цього товару. Ми не знайшли у ньому
              вашого алергену лише тому, що перевіряти не було чого — обов'язково
              прочитайте склад на упаковці.
            </p>
          )}
          {alt.over_threshold && (
            <p className="over-note">
              ⚠️ Цей варіант дорожчий за ваш ціновий поріг. Ми показуємо його лише
              тому, що в межах порогу товару без вашого алергену не знайшлось.
            </p>
          )}
          <button className="btn" style={{ marginTop: 12 }} onClick={() => { onSwitch(item.slug); onClose() }}>
            {useAlt ? 'Повернути оригінал' : 'Замінити на цей варіант'}
          </button>
        </div>
      )}

      {over.length > 0 && (
        <div className="card plain">
          <button className="disclose" onClick={() => setShowOver((v) => !v)}>
            <span>Поза вашим ціновим порогом · {over.length}</span>
            <span className="chev">{showOver ? '−' : '+'}</span>
          </button>
          {showOver && (
            <>
              {over.map((o) => (
                <div className="over-item" key={o.slug}>
                  <span>{o.name}</span>
                  <span className="op">{Math.round(o.price)} ₴</span>
                </div>
              ))}
              <p className="over-note">
                Ці варіанти дорожчі за вашу межу, тому ми їх не підставляємо.
                {onOpenSettings && (
                  <> Поріг змінюється в <button className="inline-link" onClick={onOpenSettings}>налаштуваннях</button>.</>
                )}
              </p>
            </>
          )}
        </div>
      )}
    </Sheet>
  )
}
