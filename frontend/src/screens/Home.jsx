import Screen from '../components/Screen'

/**
 * Головний екран — не дашборд і не мораль, а перелік знахідок агента.
 * Обіцянка продукту: історія покупок перетворюється на рішення для наступної.
 */
const ICONS = { promo: '🏷️', health: '🥗', alternative: '🔄', usual: '🛒' }

export default function Home({ plan, building, onOpenPlan, onOpenInsights, onRefresh }) {
  if (building && !plan?.has_data) {
    return (
      <Screen title="Нутрі-Кошик">
        <div className="center">
          <div className="spinner" />
          Читаю ваші чеки й шукаю можливості…
        </div>
      </Screen>
    )
  }

  if (!plan?.has_data) {
    return (
      <Screen title="Нутрі-Кошик" action={<button className="btn" onClick={onRefresh}>Оновити</button>}>
        <div>
          <h1>Поки нема з чого починати</h1>
          <p className="lede">{plan?.reason || 'Ми не знайшли ваших чеків Сільпо за останні тижні.'}</p>
        </div>
      </Screen>
    )
  }

  const { findings = [], summary = {} } = plan
  const totalSaving = Math.round((summary.promo_savings || 0) + (summary.alternative_savings || 0))

  return (
    <Screen
      title="Нутрі-Кошик"
      action={<button className="btn" onClick={onOpenPlan}>Переглянути план покупки</button>}
    >
      <div>
        <h1>Наступна покупка</h1>
        <p className="lede">
          Я подивився ваші покупки за {summary.based_on_weeks} тижнів і знайшов
          {' '}{findings.length} речі, які варті уваги.
        </p>
      </div>

      {totalSaving > 0 && (
        <div className="hero-money">
          <div className="hero-money-value">−{totalSaving} ₴</div>
          <div className="hero-money-label">можна зекономити на цій покупці</div>
        </div>
      )}

      <div className="findings">
        {findings.map((f) => (
          <button className="finding" key={f.kind} onClick={onOpenPlan}>
            <span className="finding-ico">{ICONS[f.kind] || '•'}</span>
            <span className="finding-body">
              <span className="finding-top">
                <span className="finding-title">{f.title}</span>
                <span className={`finding-value${f.kind === 'usual' ? '' : ' money'}`}>{f.value}</span>
              </span>
              {f.detail && <span className="finding-detail">{f.detail}</span>}
            </span>
          </button>
        ))}
      </div>

      <button className="link-row" onClick={onOpenInsights}>
        <span>Мої покупки — витрати, категорії, динаміка</span>
        <span className="chev">›</span>
      </button>

      <p className="muted">
        Нічого не потрапляє в кошик без вашого підтвердження.
      </p>
    </Screen>
  )
}
