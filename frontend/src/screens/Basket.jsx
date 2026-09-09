import Screen from '../components/Screen'

const GROUP_LABELS = {
  veg_fruit: 'Овочі та фрукти', protein: 'Білкові продукти', grains: 'Крупи та хліб',
  dairy: 'Молочні продукти', sweet_drinks: 'Напої', ultra_processed: 'Оброблені продукти',
  alcohol: 'Алкоголь', other: 'Інше',
}

export default function Basket({ draft, summary, answer, onNext, onBack }) {
  const groups = draft.reduce((acc, item) => {
    const key = item.category || 'other'
    ;(acc[key] = acc[key] || []).push(item)
    return acc
  }, {})

  const spent = summary?.total_price || 0
  const budget = summary?.budget
  const saved = summary?.saved_on_promotions || 0
  const fill = budget ? Math.min((spent / budget) * 100, 100) : 100

  return (
    <Screen
      title="Твій кошик"
      onBack={onBack}
      action={<button className="btn" onClick={onNext}>Обрати дію</button>}
    >
      {answer && <p className="lede" style={{ marginTop: 0 }}>{answer}</p>}

      {Object.entries(groups).map(([key, items]) => (
        <div key={key}>
          <div className="group-title">{GROUP_LABELS[key] || key}</div>
          {items.map((i) => (
            <div className="line" key={i.slug}>
              <div style={{ minWidth: 0 }}>
                <div className="name">{i.name}</div>
                <div className="qty">{i.quantity} шт</div>
                {i.on_promotion && i.saved > 0 && (
                  <div className="was">
                    <s>було: {Math.round(i.old_price)} ₴</s>
                    <span className="badge-amber">−{Math.round(i.saved)} ₴</span>
                  </div>
                )}
                {i.reason && <div className="qty" style={{ marginTop: 4 }}>{i.reason}</div>}
              </div>
              <div className="price">{Math.round(i.price * i.quantity)} ₴</div>
            </div>
          ))}
        </div>
      ))}

      <div className="summary">
        <div className="row" style={{ borderTop: 'none', marginTop: 0, paddingTop: 0 }}>
          <span className="k">Бюджет тижня</span>
          <span className="v">
            {Math.round(spent).toLocaleString('uk-UA')}
            {budget ? ` / ${Math.round(budget).toLocaleString('uk-UA')}` : ''} ₴
          </span>
        </div>
        <div className="progress"><i style={{ width: `${fill}%` }} /></div>
        {saved > 0 ? (
          <p className="muted">
            Завдяки акціям заощаджено <b className="v money">{Math.round(saved)} ₴</b>
          </p>
        ) : (
          <p className="muted">Акційних позицій у цьому кошику немає.</p>
        )}
      </div>
    </Screen>
  )
}
