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
  blocked: { text: 'Не за профілем', tone: 'warn' },
}

export default function ShoppingPlan({
  plan, chosen, onToggle, onSwitch, onOpenItem, onNext, onBack, onOpenSettings, busy,
}) {
  const items = plan?.items || []
  const summary = plan?.summary || {}
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
        <button className="btn" onClick={onNext} disabled={!selected.length || busy}>
          {busy
            ? 'Додаємо в кошик…'
            : `Додати схвалене в кошик · ${selected.length} · ${Math.round(total)} ₴`}
        </button>
      }
    >
      <div>
        <h1>Ваш звичний набір</h1>
        <p className="lede">
          Тільки те, що ви берете <b>регулярно</b> — з покупками, розкиданими
          по різних тижнях, а не злиплими в один похід.
        </p>
      </div>

      {['weekly', 'biweekly', 'monthly'].map((cadence) => {
        const group = items.filter((i) => (i.cadence || 'weekly') === cadence)
        if (!group.length) return null
        const label = { weekly: 'Щотижня', biweekly: 'Раз на два тижні', monthly: 'Раз на місяць' }[cadence]
        return (
          <div key={cadence}>
            <div className="group-title">{label}</div>
            <div className="plan-list">
              {group.map((i) => {
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
                  <button className="plan-name link" onClick={() => onOpenItem(i.slug)}>
                    {useAlt ? alt.name : i.name}
                  </button>
                  <span className="plan-price">
                    {Math.round((useAlt ? alt.price : i.price) * i.quantity)} ₴
                  </span>
                </div>

                <div className="plan-meta">
                  <span>{i.quantity} шт</span>
                  {i.habit?.label && (
                    <span className="tag good">{i.habit.label}</span>
                  )}
                  {i.brand_indifferent && (
                    <span className="tag">марка не принципова</span>
                  )}
                  {i.times_bought > 1 && <span>· {i.times_bought} походи</span>}
                  {label.text !== 'Лишити' && (
                    <span className={`tag ${label.tone}`}>{label.text}</span>
                  )}
                </div>

                {i.kind_note && (
                  <div className="plan-note">{i.kind_note}</div>
                )}
                {i.agent_why && (
                  <div className="plan-note agent">{i.agent_why}</div>
                )}
                {i.evidence?.length > 0 && (
                  <button className="why" onClick={() => onOpenItem(i.slug)}>
                    Чому я це пропоную →
                  </button>
                )}
                {i.alternative_rejected && (
                  <div className="plan-note agent">
                    🤖 Заміну «{i.alternative_rejected.name}» відхилив: {i.alternative_rejected.why}
                  </div>
                )}
                {i.note && !useAlt && (
                  <div className={`plan-note${i.action === 'blocked' ? ' warn' : ''}`}>{i.note}</div>
                )}
                {i.cadence !== 'weekly' && (
                  <div className="plan-meta"><span>{i.cadence_label} · не щотижнева витрата</span></div>
                )}

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
                          {alt.composition_known === false && '⚠️ '}
                          {alt.name} — {alt.why}
                          {alt.saved > 0 && <b className="delta down"> −{Math.round(alt.saved)} ₴</b>}
                          {alt.saved < 0 && <b className="delta up"> +{Math.round(-alt.saved)} ₴</b>}
                        </>
                      )}
                    </span>
                    <span className="alt-action">{useAlt ? 'Лишити своє' : 'Взяти це'}</span>
                  </button>
                )}
              </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

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

      {summary.price_tolerance_label && (
        <p className="over-note" style={{ textAlign: 'center', marginTop: -8 }}>
          Заміни підбирались із порогом «{summary.price_tolerance_label}»
          {summary.hidden_by_threshold > 0 && ` · ${summary.hidden_by_threshold} дорожчих сховано`}
          {onOpenSettings && (
            <> · <button className="inline-link" onClick={onOpenSettings}>змінити</button></>
          )}
        </p>
      )}
    </Screen>
  )
}
