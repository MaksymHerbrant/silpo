import { useEffect, useState } from 'react'
import Screen from '../components/Screen'
import { api } from '../lib/api'
import { useCart } from '../lib/cart'

/**
 * Кошик застосунку — збірна точка з усіх екранів.
 *
 * Рейтинг корисності тут ПАСИВНИЙ: чіп біля «Оформити», не попап і не окремий
 * екран. Опитування: рейтинг корисний лише для 50%, 40% нейтральні, а 52%
 * практично не читають склад — отже функція не повинна вимагати уваги.
 */
const SOURCE_LABEL = {
  plan: 'зі списку', promo: 'з акцій', nutrition: 'з харчування', analytics: 'з аналітики',
}

export default function Cart({ busy, onCheckout, onList, onOpenNutrition }) {
  const { cart, setQuantity, remove } = useCart()
  const [badge, setBadge] = useState(null)

  // Рейтинг пасивний: перераховується сам, нічого не питає і нічого не блокує
  useEffect(() => {
    if (!cart.items.length) { setBadge(null); return }
    let alive = true
    api.cartRating()
      .then((r) => { if (alive) setBadge(r.rating) })
      .catch(() => {})
    return () => { alive = false }
  }, [cart.items])

  if (!cart.items.length) {
    return (
      <Screen title="Кошик" tabs>
        <div className="center">
          <div style={{ fontSize: 34, marginBottom: 10 }}>🧺</div>
          Кошик порожній
          <p className="muted" style={{ marginTop: 8 }}>
            Додавайте товари кнопкою «+» з будь-якого екрана — вони збиратимуться тут.
          </p>
        </div>
      </Screen>
    )
  }

  return (
    <Screen
      title="Кошик"
      tabs
      action={
        <>
          {badge && (
            <button className={`health-chip ${badge.tone}`} onClick={onOpenNutrition}>
              <span className="hc-dot" aria-hidden="true" />
              <span>{badge.label}</span>
              <span className="chev">›</span>
            </button>
          )}
          <button className="btn" onClick={onCheckout} disabled={busy}>
            {busy ? 'Надсилаємо в Сільпо…' : `Оформити · ${Math.round(cart.total)} ₴`}
          </button>
          <button className="btn ghost" style={{ marginTop: 8 }} onClick={onList} disabled={busy}>
            Зробити список для магазину
          </button>
        </>
      }
    >
      <div>
        <h1>{cart.positions} позицій</h1>
        <p className="lede">
          Це кошик застосунку. У Сільпо він потрапить одним записом, коли натиснете «Оформити».
        </p>
      </div>

      <div className="card plain">
        {cart.items.map((i) => (
          <div className="cart-row" key={i.id}>
            {i.image
              ? <img className="cart-img" src={i.image} alt="" loading="lazy" />
              : <span className="cart-img ph" />}
            <div className="cart-body">
              <div className="cart-name">{i.name}</div>
              <div className="plan-meta">
                <span>{Math.round(i.price)} ₴ / шт</span>
                {i.source && <span>· {SOURCE_LABEL[i.source] || i.source}</span>}
              </div>
            </div>
            <div className="qty">
              <button onClick={() => setQuantity(i.id, i.quantity - 1)} aria-label="Менше">−</button>
              <span>{i.quantity}</span>
              <button onClick={() => setQuantity(i.id, i.quantity + 1)} aria-label="Більше">+</button>
            </div>
            <button className="cart-del" onClick={() => remove(i.id)} aria-label="Прибрати">×</button>
          </div>
        ))}
      </div>

      <div className="summary">
        <div className="row" style={{ borderTop: 'none', marginTop: 0, paddingTop: 0 }}>
          <span className="k">Разом</span>
          <span className="v">{Math.round(cart.total)} ₴</span>
        </div>
      </div>
    </Screen>
  )
}
