import Screen from '../components/Screen'

/**
 * План покупки: кожен рядок — рішення, яке приймає гість.
 * keep — лишити, switch — замінити, add — акція, review — є дешевший аналог.
 */
const ACTION_LABEL = {
  keep: { text: 'Лишити', tone: '' },
  switch: { text: 'Замінити', tone: 'good' },
  add: { text: 'Акція', tone: 'money' },
  review: { text: 'Є дешевше', tone: 'money' },
}

export default function ShoppingPlan({
  plan, chosen, onToggle, onSwitch, onNext, onBack,
}) {
  const items = plan?.items || []
  const selected = items.filter((i) => chosen[i.slug]?.selected)
  const total = selected.reduce((sum, i) => {
    const alt = chosen[i.slug]?.useAlternative ? i.alternative : null
    return sum + (alt ? alt.price : i.price) * i.quantity
  }, 0)
  const saved = selected.reduce((sum, i) => {
    const useAlt = chosen[i.slug]?.useAlternative && i.alternative
    return sum + (useAlt ? i.alternative.saved * i.quantity : (i.on_promotion ? i.saved * i.quantity : 0))
  }, 0)

  return (
    <Screen
      title="План покупки"
      onBack={onBack}
      action={
        <button className="btn" onClick={onNext} disabled={!selected.length}>
          Далі · {selected.length} товар(ів) · {Math.round(total)} ₴
        </button>
      }
    >
      <div>
        <h1>Ваш звичний набір</h1>
        <p className="lede">
          Зібраний із ваших покупок. Зніміть позначку з того, що не потрібне,
          або перемкніться на знайдену альтернативу.
        </p>
      </div>

      <div className="plan-list">
        {items.map((i) => {
          const state = chosen[i.slug] || {}
          const alt = i.alternative
          const useAlt = state.useAlternative && alt
          const label = ACTION_LABEL[i.action] || ACTION_LABEL.keep
          return (
            <div className={`plan-row${state.selected ? '' : ' off'}`} key={i.slug}>
              <button
                className={`tick${state.selected ? ' on' : ''}`}
                onClick={() => onToggle(i.slug)}
                aria-label={state.selected ? 'Прибрати зі списку' : 'Додати до списку'}
              >
                {state.selected ? '✓' : ''}
              </button>

              <div className="plan-body">
                <div className="plan-top">
                  <span className="plan-name">{useAlt ? alt.name : i.name}</span>
                  <span className="plan-price">
                    {Math.round((useAlt ? alt.price : i.price) * i.quantity)} ₴
                  </span>
                </div>

                <div className="plan-meta">
                  <span>{i.quantity} шт</span>
                  {i.times_bought > 1 && <span>· берете {i.times_bought} раз(и)</span>}
                  {label.text !== 'Лишити' && (
                    <span className={`tag ${label.tone}`}>{label.text}</span>
                  )}
                </div>

                {i.note && !useAlt && <div className="plan-note">{i.note}</div>}

                {alt && (
                  <button
                    className={`alt-row${useAlt ? ' active' : ''}`}
                    onClick={() => onSwitch(i.slug)}
                  >
                    <span className="alt-text">
                      {useAlt ? (
                        <>Повернути «{i.name}» за {Math.round(i.price)} ₴</>
                      ) : (
                        <>
                          {alt.name} — {alt.why}
                          {alt.saved > 0 && <b className="money"> −{Math.round(alt.saved)} ₴</b>}
                        </>
                      )}
                    </span>
                    <span className="alt-action">{useAlt ? 'Повернути' : 'Замінити'}</span>
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="summary">
        <div className="row" style={{ borderTop: 'none', marginTop: 0, paddingTop: 0 }}>
          <span className="k">Разом</span>
          <span className="v">{Math.round(total)} ₴</span>
        </div>
        {saved > 0 && (
          <div className="row">
            <span className="k">З них зекономлено</span>
            <span className="v money">−{Math.round(saved)} ₴</span>
          </div>
        )}
      </div>
    </Screen>
  )
}
