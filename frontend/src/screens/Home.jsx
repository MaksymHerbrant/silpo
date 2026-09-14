import Screen from '../components/Screen'
import Icon from '../components/Icon'

/**
 * Головний екран. Відповідає на одне питання за десять секунд:
 * «що GreenCart для мене знайшов?»
 *
 * Свідомо НЕ дашборд. Аналітика — це доказ під рекомендацією, а не продукт,
 * тому цифри витрат живуть в «Інсайтах», а тут — можливості й одна дія.
 */
function Money({ value }) {
  if (!value) return null
  return <span className="opp-money">{Math.round(value)} ₴</span>
}

export default function Home({ plan, onOpenPlan, onOpenOpportunity, onOpenInsights, onRefresh }) {
  if (plan?.building || (!plan && !plan?.has_data)) {
    return (
      <Screen title="GreenCart" tabs>
        <div className="boot">
          <div className="spinner" />
          <p className="boot-phase">{plan?.phase || 'Читаю ваші покупки…'}</p>
          <p className="muted">
            Перший раз це займає близько пів хвилини. Далі — миттєво.
          </p>
        </div>
      </Screen>
    )
  }

  if (!plan?.has_data) {
    const failed = Boolean(plan?.error)
    return (
      <Screen title="GreenCart" tabs
              action={<button className="btn" onClick={onRefresh}>Спробувати ще раз</button>}>
        <div>
          <h1>{failed ? 'Не вдалось прочитати дані' : 'Поки нема з чого починати'}</h1>
          <p className="lede">
            {plan?.reason || 'Не знайшли ваших чеків Сільпо. Потрібно кілька покупок із карткою.'}
          </p>
        </div>
      </Screen>
    )
  }

  const { profile, summary = {}, opportunities: opp } = plan
  const list = opp?.items || []
  const saving = opp?.total_saving || 0
  const basket = opp?.basket || {}

  return (
    <Screen
      title="GreenCart"
      tabs
      action={
        <button className="btn" onClick={onOpenPlan}>
          Переглянути план · {basket.count} товарів
        </button>
      }
    >
      <div>
        <h1>
          {profile?.name ? `${profile.name}, ` : ''}ваша наступна покупка
        </h1>
        <p className="lede">
          Переглянув {summary.receipts} ваших чеків за {Math.round(summary.based_on_weeks)} тижнів
          {list.length > 0
            ? <> і знайшов <b>{list.length} можливості</b>.</>
            : <>. Нічого термінового не знайшов — кошик готовий.</>}
        </p>
      </div>

      {saving > 0 && (
        <div className="save-hero">
          <div className="save-value">{Math.round(saving)} ₴</div>
          <div className="save-label">можна зекономити на наступній покупці</div>
        </div>
      )}

      <div className="opps">
        {list.map((o) => (
          <button className="opp" key={o.kind} onClick={() => onOpenOpportunity(o.kind)}>
            <span className="opp-ico">{o.icon}</span>
            <span className="opp-body">
              <span className="opp-top">
                <span className="opp-title">{o.title}</span>
                <Money value={o.saving} />
              </span>
              {o.detail && <span className="opp-detail">{o.detail}</span>}
            </span>
            <span className="chev">›</span>
          </button>
        ))}
      </div>

      <button className="basket-card" onClick={onOpenPlan}>
        <span className="bc-top">
          <span className="bc-title"><Icon name="basket" size={18} /> Ваш звичний набір готовий</span>
          <span className="bc-total">{Math.round(basket.total || 0)} ₴</span>
        </span>
        <span className="bc-sub">
          {basket.count} товарів, які ви берете за звичкою
          {basket.weekly ? ` · ${Math.round(basket.weekly)} ₴ щотижня` : ''}
        </span>
      </button>

      <button className="link-row" onClick={onOpenInsights}>
        <span>Звідки ці цифри</span>
        <span className="chev">›</span>
      </button>
    </Screen>
  )
}
