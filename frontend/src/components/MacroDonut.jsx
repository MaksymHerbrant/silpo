import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

/**
 * Розподіл енергії кошика по макронутрієнтах.
 * Три категорії -> легенда обов'язкова, значення підписані прямо в ній.
 */
const SERIES = [
  { key: 'protein', name: 'Білки', color: 'var(--c-protein)' },
  { key: 'fat', name: 'Жири', color: 'var(--c-fat)' },
  { key: 'carbs', name: 'Вуглеводи', color: 'var(--c-carbs)' },
]

export default function MacroDonut({ shares, totals }) {
  const data = SERIES.map((s) => ({ ...s, value: shares?.[s.key] ?? 0 }))
  const grams = { protein: totals?.protein, fat: totals?.fat, carbs: totals?.carbs }

  return (
    <>
      <div style={{ position: 'relative' }}>
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={54} outerRadius={78}
                 paddingAngle={2} stroke="var(--tg-bg)" strokeWidth={2} isAnimationActive={false}>
              {data.map((d) => <Cell key={d.key} fill={d.color} />)}
            </Pie>
            <Tooltip
              formatter={(v, n) => [`${v}% енергії`, n]}
              contentStyle={{
                background: 'var(--tg-bg)', border: 'none', borderRadius: 12,
                color: 'var(--tg-text)', fontSize: 12, boxShadow: 'var(--shadow)',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
        }}>
          <div style={{ fontSize: 20, fontWeight: 680, letterSpacing: '-.02em' }}>
            {Math.round(totals?.calories || 0)}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>ккал у кошику</div>
        </div>
      </div>
      <div className="legend">
        {data.map((d) => (
          <span key={d.key}>
            <i className="dot" style={{ background: d.color }} />
            {d.name} {d.value}% · {Math.round(grams[d.key] || 0)} г
          </span>
        ))}
      </div>
    </>
  )
}
