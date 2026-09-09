import Screen from '../components/Screen'

export default function ShoppingList({ list, onBack }) {
  return (
    <Screen title="Список для магазину" onBack={onBack}>
      <div>
        <h1>Список покупок</h1>
        <p className="lede">За категоріями — у порядку обходу магазину.</p>
      </div>
      {(list?.groups || []).map((g) => (
        <div key={g.category}>
          <div className="group-title">{g.label}</div>
          {g.items.map((i, idx) => (
            <div className="line" key={idx}>
              <div style={{ minWidth: 0 }}>
                <div className="name">{i.name}</div>
                <div className="qty">
                  {i.quantity} шт{i.on_promotion ? ' · в акції' : ''}
                </div>
              </div>
              <div className="price">{Math.round(i.price || 0)} ₴</div>
            </div>
          ))}
        </div>
      ))}
    </Screen>
  )
}
