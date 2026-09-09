import Sheet from '../components/Sheet'

/** Глибока деталізація однієї позиції: історія, склад, алергени, акція. */
export default function ItemDetail({ item, onClose, onSwitch, chosen }) {
  if (!item) return null
  const d = item.detail || {}
  const alt = item.alternative
  const useAlt = chosen?.useAlternative

  return (
    <Sheet title={item.name} onClose={onClose}>
      {item.image && (
        <img src={item.image} alt="" style={{
          width: 96, height: 96, objectFit: 'contain', borderRadius: 14,
          background: 'var(--surface)', alignSelf: 'center',
        }} />
      )}

      <div className={`verdict ${item.allergen_hits?.length ? 'bad' : 'ok'}`}>
        <b>{item.allergen_hits?.length ? '⛔ ' : '✓ '}</b>
        {d.allergen_check}
        {item.allergen_hits?.map((h, i) => (
          <div key={i} style={{ marginTop: 6 }}>
            <b>{h.restriction}</b> — знайдено у складі: …{h.matched}…
          </div>
        ))}
      </div>

      <div className="card plain">
        <h3 style={{ marginBottom: 8 }}>Чому в кошику</h3>
        <p className="muted">{d.why}</p>
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
          <button className="btn" style={{ marginTop: 12 }} onClick={() => { onSwitch(item.slug); onClose() }}>
            {useAlt ? 'Повернути оригінал' : 'Замінити на цей варіант'}
          </button>
        </div>
      )}
    </Sheet>
  )
}
