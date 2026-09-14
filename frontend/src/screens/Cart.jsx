import { useEffect, useState } from 'react'
import AddToCartButton from '../components/AddToCartButton'
import Screen from '../components/Screen'
import Thumb from '../components/Thumb'
import Icon from '../components/Icon'
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
  const { cart, setQuantity, remove, add, setCart } = useCart()
  const [badge, setBadge] = useState(null)
  const [silpo, setSilpo] = useState(null)
  const [pulling, setPulling] = useState(false)

  // Кошик Сільпо читаємо наживо: він змінюється незалежно від застосунку
  useEffect(() => {
    let alive = true
    api.silpoCart().then((r) => { if (alive) setSilpo(r) }).catch(() => {})
    return () => { alive = false }
  }, [])

  async function pullFromSilpo() {
    setPulling(true)
    try { setCart(await api.importSilpoCart()) } finally { setPulling(false) }
  }

  // Рейтинг пасивний: перераховується сам, нічого не питає і нічого не блокує
  useEffect(() => {
    if (!cart.items.length) { setBadge(null); return }
    let alive = true
    api.cartRating()
      .then((r) => { if (alive) setBadge(r.rating) })
      .catch(() => {})
    return () => { alive = false }
  }, [cart.items])

  const silpoBlock = silpo?.available && silpo.count > 0 && (
    <div className="card">
      <div className="section-row">
        <h3>Уже у вашому кошику Сільпо</h3>
        <span className="muted">{silpo.count} · {Math.round(silpo.total)} ₴</span>
      </div>
      {silpo.items.slice(0, 5).map((i) => (
        <div className="hist-row" key={i.product_id || i.name}>
          <span>{i.quantity}× {i.name}</span>
          <span className="d">{Math.round(i.price)} ₴</span>
        </div>
      ))}
      <button className="btn ghost" style={{ marginTop: 12 }}
              onClick={pullFromSilpo} disabled={pulling}>
        {pulling ? 'Переношу…' : 'Забрати до себе, щоб редагувати'}
      </button>
    </div>
  )

  const forgottenBlock = silpo?.available && silpo.forgotten?.length > 0 && (
    <div className="card">
      <div className="section-row">
        <h3>Можливо, забули</h3>
        <span className="muted">{silpo.forgotten_total} зі звичного</span>
      </div>
      <p className="muted" style={{ marginBottom: 10 }}>
        Це те, що ви берете регулярно, але зараз його в кошику Сільпо немає.
      </p>
      {silpo.forgotten.map((f) => (
        <div className="offer" key={f.slug}>
          <Thumb src={f.image} />
          <span className="offer-body">
            <span className="offer-name">
              {f.on_promotion && <span className="tag money" style={{ marginRight: 6 }}>акція</span>}
              {f.name}
            </span>
            <span className="plan-meta"><span>{Math.round(f.price)} ₴</span><span>· {f.why}</span></span>
          </span>
          <AddToCartButton item={f} source="plan" />
        </div>
      ))}
    </div>
  )

  const betterBlock = silpo?.better?.length > 0 && (
    <div className="card">
      <div className="section-row"><h3>Є вигідніше за те, що вже в кошику</h3></div>
      <p className="muted" style={{ marginBottom: 10 }}>
        Звіряю і ваш кошик тут, і той, що вже зібраний у Сільпо.
      </p>
      {silpo.better.map((b) => (
        <div className="offer" key={b.slug}>
          <Thumb src={b.image} />
          <span className="offer-body">
            <span className="offer-name">{b.name}</span>
            <span className="plan-meta">
              <span>замість «{b.in_cart}»</span>
              <span className="delta down">{Math.round(b.saved)} ₴ дешевше</span>
            </span>
          </span>
          <AddToCartButton item={b} source="promo" />
        </div>
      ))}
    </div>
  )

  if (!cart.items.length) {
    return (
      <Screen title="Кошик" tabs>
        {silpoBlock}
        {forgottenBlock}
        {betterBlock}
        {!silpo?.count && (
          <div className="center">
            <div style={{ marginBottom: 10, color: 'var(--ink-3)' }}><Icon name="basket" size={40} /></div>
            Кошик порожній
            <p className="muted" style={{ marginTop: 8 }}>
              Додавайте товари кнопкою «+» з будь-якого екрана.
            </p>
          </div>
        )}
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

      {silpoBlock}
      {forgottenBlock}
      {betterBlock}
    </Screen>
  )
}
