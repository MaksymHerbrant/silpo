import Icon from './Icon'
/**
 * Каркас екрана: хедер, тіло, липка кнопка знизу.
 * `tabs` лишає місце під таб-бар, який App малює поверх усіх екранів.
 */
export default function Screen({ title, onBack, children, action, onSettings, tabs }) {
  return (
    <div className={`screen${tabs ? ' tabs' : ''}`}>
      <div className="top">
        {onBack ? <button onClick={onBack} aria-label="Назад">‹</button> : <span />}
        <h2>{title}</h2>
        {onSettings
          ? <button className="gear" onClick={onSettings} aria-label="Налаштування"><Icon name="settings" /></button>
          : <span className="dot" aria-hidden="true" />}
      </div>
      <div className="body fade">{children}</div>
      {action && <div className="bottom">{action}</div>}
    </div>
  )
}
