const TABS = [
  { id: 'profile', ico: '📊', label: 'Профіль' },
  { id: 'cart', ico: '🧺', label: 'Кошик' },
  { id: 'swaps', ico: '🔄', label: 'Заміни' },
  { id: 'allergens', ico: '⚠️', label: 'Алергени' },
  { id: 'debug', ico: '🛠', label: 'MCP' },
]

export default function Nav({ tab, onChange, cartCount = 0 }) {
  return (
    <nav className="nav">
      {TABS.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
                aria-current={tab === t.id ? 'page' : undefined}>
          <span className="ico" style={{ position: 'relative' }}>
            {t.ico}
            {t.id === 'cart' && cartCount > 0 && (
              <i style={{
                position: 'absolute', top: -3, right: -9, minWidth: 15, height: 15,
                borderRadius: 8, background: 'var(--tg-link)', color: '#fff',
                fontSize: 9, lineHeight: '15px', fontStyle: 'normal', padding: '0 4px',
              }}>{cartCount}</i>
            )}
          </span>
          {t.label}
        </button>
      ))}
    </nav>
  )
}
