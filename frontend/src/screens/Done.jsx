import Screen from '../components/Screen'

/** Фінал: онлайн-кошик або список для магазину. */
export default function Done({ mode, result, list, onBack, onHome }) {
  if (mode === 'cart') {
    return (
      <Screen title="Готово" onBack={onBack}
              action={<button className="btn ghost" onClick={onHome}>На головну</button>}>
        <div>
          <h1>Кошик створено</h1>
          <p className="lede">
            Додано {result.added} позицій. {result.checkout_hint}
          </p>
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 10 }}>Зараз у кошику Сільпо</h3>
          {(result.cart_now || []).map((p, i) => (
            <div className="row" key={i} style={i === 0 ? { borderTop: 'none', marginTop: 0, paddingTop: 0 } : undefined}>
              <span className="k">{p.name}</span>
              <span className="v">{p.quantity}</span>
            </div>
          ))}
        </div>
      </Screen>
    )
  }

  return (
    <Screen title="Список покупок" onBack={onBack}
            action={<button className="btn ghost" onClick={onHome}>На головну</button>}>
      <div>
        <h1>Список для магазину</h1>
        <p className="lede">
          {list.items} позицій на {Math.round(list.total_price)} ₴, за категоріями.
        </p>
      </div>
      {(list.groups || []).map((g) => (
        <div key={g.category}>
          <div className="group-title">{g.label}</div>
          {g.items.map((i, idx) => (
            <div className="plan-row" key={idx}>
              <span className="tick" aria-hidden="true" />
              <div className="plan-body">
                <div className="plan-top">
                  <span className="plan-name">{i.name}</span>
                  <span className="plan-price">{Math.round((i.price || 0) * i.quantity)} ₴</span>
                </div>
                <div className="plan-meta">
                  <span>{i.quantity} шт</span>
                  {i.on_promotion && <span className="tag money">в акції</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </Screen>
  )
}
