import Icon from './Icon'
import { useCart } from '../lib/cart'

/**
 * Кнопка «додати» доступна з КОЖНОГО екрана і ніколи не переводить на інший.
 * Тап — рядок відгукується, лічильник у таб-барі росте, гість лишається на місці.
 */
export default function AddToCartButton({ item, source }) {
  const { add, has, pending } = useCart()
  const inCart = has(item.product_id)
  const busy = Boolean(pending[item.product_id])

  return (
    <button
      className={`add-btn${inCart ? ' in' : ''}`}
      disabled={busy || !item.product_id}
      onClick={(e) => {
        e.stopPropagation()
        add({ ...item, source, decision_id: item.decision_id })
      }}
      aria-label={inCart ? `${item.name} вже в кошику, додати ще` : `Додати ${item.name} до кошика`}
    >
      {busy ? '…' : inCart ? <Icon name="check" size={16} /> : '+'}
    </button>
  )
}
