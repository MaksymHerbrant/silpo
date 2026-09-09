import Sheet from '../components/Sheet'

/** Деталізація смарт-картки з головного екрана. */
export default function CardDetail({ kind, plan, onClose, onOpenItem }) {
  const { profile, findings = [], items = [], noise = [], summary = {} } = plan || {}
  const finding = findings.find((f) => f.kind === kind)
  const related = items.filter((i) => finding?.slugs?.includes(i.slug))

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
              Дані беруться з анкети, яку ви заповнювали в застосунку Сільпо.
              Ми їх не вигадуємо і не змінюємо.
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
