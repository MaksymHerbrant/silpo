import { useCart } from '../lib/cart'

/** П'ять екранів застосунку. Кошик несе лічильник — він росте з будь-якого таба. */
const TABS = [
  { key: 'home', icon: '✨', label: 'Головна' },
  { key: 'promos', icon: '🏷️', label: 'Вигода' },
  { key: 'cart', icon: '🧺', label: 'Кошик' },
  { key: 'analytics', icon: '📊', label: 'Інсайти' },
  { key: 'settings', icon: '⚙️', label: 'Ще' },
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
            {t.icon}
            {t.key === 'cart' && cart.count > 0 && <span className="tab-badge">{cart.count}</span>}
          </span>
          <span className="tab-label">{t.label}</span>
        </button>
      ))}
    </nav>
  )
}
