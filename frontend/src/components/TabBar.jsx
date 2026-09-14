import { useCart } from '../lib/cart'
import Icon from './Icon'

/** П'ять екранів застосунку. Кошик несе лічильник — він росте з будь-якого таба. */
const TABS = [
  { key: 'home', icon: 'home', label: 'Головна' },
  { key: 'promos', icon: 'tag', label: 'Вигода' },
  { key: 'cart', icon: 'basket', label: 'Кошик' },
  { key: 'analytics', icon: 'chart', label: 'Інсайти' },
  { key: 'settings', icon: 'dots', label: 'Ще' },
]

export default function TabBar({ active, onChange }) {
  const { cart } = useCart()
  return (
    <nav className="tabbar" aria-label="Основна навігація">
      {TABS.map((t) => (
        <button
          key={t.key}
          className={`tab${active === t.key ? ' on' : ''}`}
          aria-current={active === t.key ? 'page' : undefined}
          onClick={() => onChange(t.key)}
        >
          <span className="tab-ico">
            <Icon name={t.icon} size={22} />
            {t.key === 'cart' && cart.count > 0 && <span className="tab-badge">{cart.count}</span>}
          </span>
          <span className="tab-label">{t.label}</span>
        </button>
      ))}
    </nav>
  )
}
