import Screen from '../components/Screen'

/**
 * Один екран — стрічка смарт-карток. Ніяких вкладок і простирадл.
 * Кожна картка клікабельна й відкриває деталізацію.
 */
const FINDING_ICON = {
  safety: '⛔', preference: '🎯', promo: '🏷️', health: '🥗',
  alternative: '🔄', noise: '🧹', usual: '🛒',
}

export default function Dashboard({ plan, building, onOpenCard, onOpenItem, onOpenPlan, onRefresh }) {
  if (building && !plan?.has_data) {
    return (
      <Screen title="GreenCart">
        <div className="center">
          <div className="spinner" />
          Читаю ваші чеки, профіль і акції…
        </div>
      </Screen>
    )
  }

  if (!plan?.has_data) {
    return (
      <Screen title="GreenCart" action={<button className="btn" onClick={onRefresh}>Оновити</button>}>
        <div>
          <h1>Поки нема з чого починати</h1>
          <p className="lede">{plan?.reason || 'Не знайшли ваших чеків Сільпо.'}</p>
        </div>
      </Screen>
    )
  }

  const { profile, findings = [], summary = {}, items = [] } = plan
  const saving = Math.round((summary.promo_savings || 0) + (summary.alternative_savings || 0))
  const basket = items.filter((i) => i.action !== 'blocked')
  const preview = basket.slice(0, 4)

  return (
    <Screen
      title="GreenCart"
      action={<button className="btn" onClick={onOpenPlan}>Переглянути кошик · {summary.items} товарів</button>}
    >
      <div>
        <h1>{profile?.name ? `${profile.name}, ваша наступна покупка` : 'Ваша наступна покупка'}</h1>
        <p className="lede">
          Зібрано з {summary.receipts} чеків за {summary.based_on_weeks} тижнів.
        </p>
      </div>

      <button
        className={`status-bar${profile?.status?.active ? ' on' : ''}`}
        onClick={() => onOpenCard('profile')}
      >
        <span className="status-ico">{profile?.status?.active ? '🛡️' : '👤'}</span>
        <span className="status-body">
          <span className="status-title">{profile?.status?.title}</span>
          <span className="status-detail">{profile?.status?.detail}</span>
        </span>
        <span className="chev">›</span>
      </button>

      <div className="agent-report" onClick={() => onOpenCard('noise')} role="button" tabIndex={0}>
        <div className="agent-report-row">
          <div>
            <div className="ar-value">{summary.filtered_count}</div>
            <div className="ar-label">випадкових позицій відсіяно</div>
          </div>
          <div>
            <div className="ar-value money">−{saving} ₴</div>
            <div className="ar-label">можлива економія</div>
          </div>
          <div>
            <div className="ar-value">{summary.blocked || 0}</div>
            <div className="ar-label">заблоковано за профілем</div>
          </div>
        </div>
      </div>

      <div className="findings">
        {findings.map((f) => (
          <button className="finding" key={f.kind} onClick={() => onOpenCard(f.kind)}>
            <span className="finding-ico">{FINDING_ICON[f.kind] || '•'}</span>
            <span className="finding-body">
              <span className="finding-top">
                <span className="finding-title">{f.title}</span>
                <span className={`finding-value${['promo', 'alternative'].includes(f.kind) ? ' money' : ''}`}>
                  {f.value}
                </span>
              </span>
              {f.detail && <span className="finding-detail">{f.detail}</span>}
            </span>
            <span className="chev">›</span>
          </button>
        ))}
      </div>

      <div className="card">
        <div className="section-row">
          <h3>Звичний кошик</h3>
          <span className="muted">{summary.total_price} ₴</span>
        </div>
        <div className="strip">
          {preview.map((i) => (
            <button className="strip-item" key={i.slug} onClick={() => onOpenItem(i.slug)}>
              {i.image
                ? <img src={i.image} alt="" loading="lazy" />
                : <span className="strip-ph" />}
              <span className="strip-name">{i.name}</span>
              <span className="strip-price">
                {Math.round(i.price)} ₴
                {i.on_promotion && <b className="money"> −{Math.round(i.saved)}</b>}
              </span>
            </button>
          ))}
          {basket.length > preview.length && (
            <button className="strip-item more" onClick={onOpenPlan}>
              <span className="strip-more">+{basket.length - preview.length}</span>
              <span className="strip-name">ще товарів</span>
            </button>
          )}
        </div>
      </div>
    </Screen>
  )
}
