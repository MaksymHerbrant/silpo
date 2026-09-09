/** Каркас екрана з макетів: хедер, тіло, липка кнопка знизу. */
export default function Screen({ title, onBack, children, action }) {
  return (
    <div className="screen">
      <div className="top">
        {onBack ? <button onClick={onBack} aria-label="Назад">‹</button> : <span />}
        <h2>{title}</h2>
        <span className="dot" aria-hidden="true" />
      </div>
      <div className="body fade">{children}</div>
      {action && <div className="bottom">{action}</div>}
    </div>
  )
}
