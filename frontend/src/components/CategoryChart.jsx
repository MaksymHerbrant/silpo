import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

/**
 * На що йдуть гроші. Одна серія (частка витрат), тому легенда не потрібна —
 * кожен стовпчик підписаний прямо. Категорії-маркери підсвічуємо.
 */
const ATTENTION = new Set(['Солодке й снеки', 'Солодкі напої', 'Алкоголь'])
const GOOD = new Set(['Овочі й фрукти', 'Мʼясо й риба'])

export default function CategoryChart({ categories }) {
  const data = (categories || []).slice(0, 7).map((c) => ({
    name: c.name, share: c.share, spend: c.spend,
  }))
  const color = (name) =>
    ATTENTION.has(name) ? 'var(--c-fat)' : GOOD.has(name) ? 'var(--c-carbs)' : 'var(--c-protein)'

  return (
    <ResponsiveContainer width="100%" height={Math.max(data.length * 34 + 16, 120)}>
      <BarChart data={data} layout="vertical" barCategoryGap={9}
                margin={{ top: 0, right: 44, bottom: 0, left: 0 }}>
        <XAxis type="number" hide domain={[0, 'dataMax']} />
        <YAxis type="category" dataKey="name" width={116} tickLine={false} axisLine={false}
               tick={{ fill: 'var(--tg-hint)', fontSize: 11.5 }} />
        <Tooltip
          cursor={{ fill: 'var(--tg-secondary-bg)' }}
          formatter={(v, _n, p) => [`${v}% · ${Math.round(p.payload.spend)} грн`, 'Частка витрат']}
          contentStyle={{
            background: 'var(--tg-bg)', border: 'none', borderRadius: 12,
            color: 'var(--tg-text)', fontSize: 12, boxShadow: 'var(--shadow)',
          }}
        />
        <Bar dataKey="share" radius={[4, 4, 4, 4]} barSize={13} isAnimationActive={false}>
          {data.map((d) => <Cell key={d.name} fill={color(d.name)} />)}
          <LabelList dataKey="share" position="right" formatter={(v) => `${v}%`}
                     style={{ fill: 'var(--tg-text)', fontSize: 11.5, fontWeight: 600 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
