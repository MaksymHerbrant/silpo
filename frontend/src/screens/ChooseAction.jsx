import { useState } from 'react'
import Screen from '../components/Screen'

/**
 * Два виходи агента. «Додати в кошик» — реальний write-виклик MCP
 * silpo_add_or_update_cart_products, перевірений на живому акаунті.
 */
export default function ChooseAction({ onApply, onList, applying, result, onBack }) {
  const [choice, setChoice] = useState('cart')

  if (result) {
    return (
      <Screen title="Готово" onBack={onBack}>
        <div>
          <h1>Кошик оновлено</h1>
          <p className="lede">
            Додано {result.added} позицій у ваш кошик Сільпо. Залишилось підтвердити
            оплату в застосунку магазину.
          </p>
        </div>
        <div className="card">
          <div className="label">Зараз у кошику Сільпо</div>
          {(result.cart_now || []).map((p, i) => (
            <div className="line" key={i}>
              <div className="name">{p.name}</div>
              <div className="price">{p.quantity}</div>
            </div>
          ))}
        </div>
      </Screen>
    )
  }

  return (
    <Screen
      title="Обери дію"
      onBack={onBack}
      action={
        <button className="btn" disabled={applying}
                onClick={() => (choice === 'cart' ? onApply() : onList())}>
          {applying ? 'Виконую…' : choice === 'cart' ? 'Додати в кошик Сільпо' : 'Показати список'}
        </button>
      }
    >
      <div>
        <h1>Кошик готовий. Що далі?</h1>
        <p className="lede">
          Онлайн-кошик або список для покупок офлайн — агент оформить будь-який варіант.
        </p>
      </div>

      <button className="choice" aria-pressed={choice === 'cart'} onClick={() => setChoice('cart')}>
        <span className="ico">🛒</span>
        <span>
          <span className="t">Додати в кошик застосунку</span>
          <span className="s">З'явиться в кошику магазину — залишиться підтвердити оплату.</span>
        </span>
      </button>

      <button className="choice" aria-pressed={choice === 'list'} onClick={() => setChoice('list')}>
        <span className="ico">📋</span>
        <span>
          <span className="t">Список для магазину</span>
          <span className="s">Категоризований чек-лист — щоб не блукати між полицями.</span>
        </span>
      </button>
    </Screen>
  )
}
