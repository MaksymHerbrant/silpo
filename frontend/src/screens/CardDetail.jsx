import Sheet from '../components/Sheet'

/** Деталізація смарт-картки з головного екрана. */
export default function CardDetail({ kind, plan, onClose, onOpenItem, onOpenSettings, onSwitch }) {
  const { profile, findings = [], items = [], noise = [], summary = {},
          emerging = [], fading = [] } = plan || {}
  const finding = findings.find((f) => f.kind === kind)
  const related = items.filter((i) => finding?.slugs?.includes(i.slug))

  if (kind === 'threshold') {
    return (
      <Sheet title="Приховано ціновим порогом" onClose={onClose}>
        <p className="muted">
          Ваша межа — «{summary.price_tolerance_label}». Ці варіанти її перевищують,
          тому в план не потрапили, але подивитись їх можна.
        </p>
        {related.map((i) => (
          <div className="card plain" key={i.slug}>
            <div className="kv">
              <span className="k">Замість «{i.name}»</span>
              <span className="v">{Math.round(i.price)} ₴</span>
            </div>
            {(i.alternatives_over || []).map((o) => (
              <div className="over-item" key={o.slug}>
                <span>{o.name}</span>
                <span className="op">{Math.round(o.price)} ₴</span>
              </div>
            ))}
          </div>
        ))}
        {onOpenSettings && (
          <button className="btn ghost" onClick={() => { onClose(); onOpenSettings() }}>
            Змінити ціновий поріг
          </button>
        )}
      </Sheet>
    )
  }

  if (kind === 'profile') {
    return (
      <Sheet title="Ваш профіль Сільпо" onClose={onClose}>
        <div className={`verdict ${profile?.status?.active ? 'ok' : 'bad'}`}>
          {profile?.status?.title}
        </div>
        <p className="muted">{profile?.status?.detail}</p>
        {profile?.restrictions?.length > 0 && (
          <div className="card plain">
            <h3 style={{ marginBottom: 8 }}>Обмеження з профілю</h3>
            {profile.restrictions.map((r) => (
              <div className="kv" key={r.slug}>
                <span className="k">{r.label}</span>
                <span className="v">активне</span>
              </div>
            ))}
            <p className="muted" style={{ marginTop: 10 }}>
              Дані — з анкети, яку ви заповнювали в застосунку Сільпо.
            </p>
          </div>
        )}
      </Sheet>
    )
  }

  if (kind === 'noise') {
    return (
      <Sheet title="Що відсіяно" onClose={onClose}>
        <p className="muted">
          Разові покупки не входять у звичний набір — інакше список засмічується
          тим, що ви взяли один раз. Систематичні супутні товари, як-от пакети,
          лишаються.
        </p>
        <div className="card plain">
          <div className="kv">
            <span className="k">Відсіяно позицій</span>
            <span className="v">{summary.filtered_count}</span>
          </div>
          <div className="kv">
            <span className="k">На суму</span>
            <span className="v">{Math.round(summary.filtered_spend || 0)} ₴</span>
          </div>
        </div>
        <div className="card plain">
          <h3 style={{ marginBottom: 8 }}>Не увійшли в набір</h3>
          {noise.map((n, i) => (
            <div className="hist-row" key={i}>
              <span>{n.name}</span>
              <span className="d">{Math.round(n.spend)} ₴</span>
            </div>
          ))}
        </div>
      </Sheet>
    )
  }

  if (kind === 'emerging' || kind === 'fading') {
    const rows = kind === 'emerging' ? emerging : fading
    return (
      <Sheet title={kind === 'emerging' ? 'Нове у вашому кошику' : 'Випало зі звички'} onClose={onClose}>
        <p className="muted">
          {kind === 'emerging'
            ? 'Ви взяли ці товари кілька разів нещодавно. Якщо покупки повторяться в різні тижні — вони стануть частиною звичного набору.'
            : 'Раніше ви брали це регулярно, а останнім часом ні. Якщо потрібно — поверніть у набір.'}
        </p>
        {rows.map((r) => (
          <div className="card plain" key={r.slug}>
            <div className="kv">
              <span className="k">{r.name}</span>
              <span className="v">{Math.round(r.spend)} ₴</span>
            </div>
            <p className="over-note">{r.reason}</p>
          </div>
        ))}
      </Sheet>
    )
  }

  if (kind === 'safety') {
    return (
      <Sheet title="Позиції з вашим алергеном" onClose={onClose}>
        <p className="muted">{finding?.detail}</p>
        {related.map((i) => (
          <div className="card plain" key={i.slug}>
            <button className="offer-body" onClick={() => { onClose(); onOpenItem(i.slug) }}>
              <span className="offer-name">{i.name}</span>
              <span className="plan-meta">
                {(i.allergen_hits || []).filter((h) => h.action === 'block').map((h, n) => (
                  <span key={n}>{h.restriction}</span>
                ))}
              </span>
            </button>
            {i.alternative ? (
              <>
                <div className="kv" style={{ marginTop: 8 }}>
                  <span className="k">Заміна: {i.alternative.name}</span>
                  <span className="v">{Math.round(i.alternative.price)} ₴</span>
                </div>
                {i.alternative.composition_known === false && (
                  <p className="over-note" style={{ color: 'var(--money)', fontWeight: 600 }}>
                    Каталог не публікує склад цієї заміни — прочитайте його на упаковці.
                  </p>
                )}
                <button
                  className="btn"
                  style={{ marginTop: 10 }}
                  onClick={() => { onSwitch?.(i.slug); onClose() }}
                >
                  Замінити на цей варіант
                </button>
              </>
            ) : (
              <p className="over-note">
                Заміни без вашого алергену в каталозі не знайшлось.
              </p>
            )}
          </div>
        ))}
      </Sheet>
    )
  }

  return (
    <Sheet title={finding?.title || 'Деталі'} onClose={onClose}>
      {finding?.detail && <p className="muted">{finding.detail}</p>}
      {related.map((i) => (
        <button className="finding" key={i.slug} onClick={() => { onClose(); onOpenItem(i.slug) }}>
          {i.image
            ? <img src={i.image} alt="" className="finding-ico" style={{ objectFit: 'contain', background: 'var(--surface-2)' }} />
            : <span className="finding-ico">•</span>}
          <span className="finding-body">
            <span className="finding-top">
              <span className="finding-title">{i.name}</span>
              <span className="finding-value">{Math.round(i.price)} ₴</span>
            </span>
            <span className="finding-detail">
              {i.note || i.kind_reason}
              {i.alternative && ` → ${i.alternative.name}`}
            </span>
          </span>
          <span className="chev">›</span>
        </button>
      ))}
    </Sheet>
  )
}
