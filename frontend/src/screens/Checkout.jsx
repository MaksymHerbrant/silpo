import { useState } from 'react'
import Screen from '../components/Screen'

/** Два виходи: онлайн-кошик Сільпо або список для покупок офлайн. */
export default function Checkout({ count, total, busy, onCart, onList, onBack }) {
  const [choice, setChoice] = useState('cart')

  return (
    <Screen
      title="Як робите покупку"
      onBack={onBack}
      action={
        <button className="btn" disabled={busy}
                onClick={() => (choice === 'cart' ? onCart() : onList())}>
          {busy ? 'Виконую…' : choice === 'cart' ? 'Створити кошик Сільпо' : 'Показати список'}
        </button>
      }
    >
      <div>
        <h1>Готово до покупки</h1>
        <p className="lede">{count} позицій на {Math.round(total)} ₴.</p>
      </div>

      <button className="choice" aria-pressed={choice === 'cart'} onClick={() => setChoice('cart')}>
        <span className="ico">🛒</span>
        <span>
          <span className="t">Онлайн-кошик</span>
          <span className="s">Товари зʼявляться в кошику Сільпо — лишиться підтвердити замовлення.</span>
        </span>
      </button>

      <button className="choice" aria-pressed={choice === 'list'} onClick={() => setChoice('list')}>
        <span className="ico">📝</span>
        <span>
          <span className="t">Список для магазину</span>
          <span className="s">Категоризований чек-лист, щоб не блукати між полицями.</span>
        </span>
      </button>
    </Screen>
  )
}
