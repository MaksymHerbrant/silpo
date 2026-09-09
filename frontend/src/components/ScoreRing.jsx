/**
 * Герой-число: оцінка кошика 0–100 + клас A–E.
 * Одне значення, тому кільце-індикатор, а не діаграма.
 * Колір дублюється текстом класу — ідентичність не тільки кольором.
 */
export default function ScoreRing({ score, letter, size = 112, stroke = 10 }) {
  const value = typeof score === 'number' ? score : 0
  const r = (size - stroke) / 2
  const circumference = 2 * Math.PI * r
  const color = value >= 70 ? 'var(--good)' : value >= 45 ? 'var(--warn)' : 'var(--bad)'

  return (
    <figure className="ring" style={{ width: size, height: size, margin: 0 }}>
      <svg width={size} height={size} role="img"
           aria-label={`Оцінка ${value} зі 100, клас ${letter || 'невідомий'}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                stroke="var(--tg-secondary-bg)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - value / 100)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset .8s cubic-bezier(.2,.8,.2,1)' }}
        />
      </svg>
      <figcaption>
        <span className="value">{typeof score === 'number' ? score : '—'}</span>
        <span className="label">КЛАС {letter || '—'}</span>
      </figcaption>
    </figure>
  )
}
