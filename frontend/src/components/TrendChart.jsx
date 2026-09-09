import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

/** Тижневий тренд оцінки. Одна серія на одній осі — без другої шкали. */
export default function TrendChart({ weeks }) {
  const data = weeks.map((w) => ({
    week: new Date(w.week_start_date).toLocaleDateString('uk-UA', { day: '2-digit', month: 'short' }),
    score: w.health_score,
  }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -26 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--c-protein)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--c-protein)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--tg-secondary-bg)" vertical={false} />
        <XAxis dataKey="week" tickLine={false} axisLine={false}
               tick={{ fill: 'var(--tg-hint)', fontSize: 11 }} />
        <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tickLine={false} axisLine={false}
               tick={{ fill: 'var(--tg-hint)', fontSize: 11 }} />
        <Tooltip
          formatter={(v) => [`${v} / 100`, 'Оцінка тижня']}
          contentStyle={{
            background: 'var(--tg-bg)', border: 'none', borderRadius: 12,
            color: 'var(--tg-text)', fontSize: 12, boxShadow: 'var(--shadow)',
          }}
        />
        <Area type="monotone" dataKey="score" stroke="var(--c-protein)" strokeWidth={2}
              fill="url(#trendFill)" dot={{ r: 3.5, strokeWidth: 2, fill: 'var(--tg-bg)' }}
              activeDot={{ r: 6 }} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
