/**
 * Порівняння часток енергії з нормами AMDR (ВООЗ/EFSA).
 * Свідомо не Recharts: тут важливо показати ДІАПАЗОН норми як тло смуги,
 * а не значення саме по собі — власна смуга робить це точніше й легше.
 */
const NORMS = {
  protein: { label: 'Білки', min: 10, max: 20, color: 'var(--c-protein)' },
  fat: { label: 'Жири', min: 20, max: 35, color: 'var(--c-fat)' },
  carbs: { label: 'Вуглеводи', min: 45, max: 60, color: 'var(--c-carbs)' },
}
const SCALE = 80 // максимум шкали, %

export default function MacroNorms({ shares, deviations }) {
  return (
    <div>
      {Object.entries(NORMS).map(([key, n]) => {
        const value = shares?.[key] ?? 0
        const deviation = deviations?.[key] ?? 0
        const status = deviation <= 0 ? 'у нормі' : value < n.min ? 'нижче норми' : 'вище норми'
        const cls = deviation <= 0 ? 'good' : deviation <= 10 ? 'warn' : 'bad'
        return (
          <div className="macro" key={key}>
            <div className="macro-head">
              <span>{n.label} — <b>{value}%</b> енергії</span>
              <span className={`pill ${cls}`}>{status}</span>
            </div>
            <div className="macro-track">
              <div className="macro-norm" style={{
                left: `${(n.min / SCALE) * 100}%`,
                width: `${((n.max - n.min) / SCALE) * 100}%`,
              }} />
              <div className="macro-fill" style={{
                width: `${Math.min((value / SCALE) * 100, 100)}%`,
                background: n.color, opacity: deviation > 0 ? 1 : 0.85,
              }} />
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
              норма ВООЗ: {n.min}–{n.max}%
            </div>
          </div>
        )
      })}
    </div>
  )
}
