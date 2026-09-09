import { useState } from 'react'
import Screen from '../components/Screen'

const GOALS = [
  { key: 'less_sugar', label: 'Менше цукру' },
  { key: 'save_money', label: 'Заощадити гроші' },
  { key: 'muscle', label: "Набрати м'язи" },
  { key: 'healthier', label: 'Здоровіший раціон' },
]

const DIETS = [
  { key: 'gluten', label: 'Без глютену' },
  { key: 'lactoza', label: 'Без лактози' },
  { key: 'vegetarian', label: 'Вегетаріанська' },
  { key: 'none', label: 'Немає' },
]

/**
 * Онбординг за 15 секунд. Стать і вік не питаємо — вони вже є в профілі Сільпо,
 * обмеження теж підтягуються звідти, ці пілюлі лише доповнюють їх.
 */
export default function Onboarding({ onDone, saving }) {
  const [goal, setGoal] = useState('less_sugar')
  const [budget, setBudget] = useState(1500)
  const [diets, setDiets] = useState([])
  const [household, setHousehold] = useState(1)

  function toggleDiet(key) {
    if (key === 'none') return setDiets([])
    setDiets((d) => (d.includes(key) ? d.filter((x) => x !== key) : [...d, key]))
  }

  return (
    <Screen
      title="Онбординг"
      action={
        <button className="btn" disabled={saving}
                onClick={() => onDone({ goal, weekly_budget: budget, diets, household_size: household })}>
          {saving ? 'Зберігаю…' : 'Почати'}
        </button>
      }
    >
      <div>
        <h1>Дай агенту напрямок</h1>
        <p className="lede">15 секунд — і він сам збере кошик під твою мету.</p>
      </div>

      <div>
        <div className="label">Головна мета</div>
        <div className="pills">
          {GOALS.map((g) => (
            <button key={g.key} className="pill" aria-pressed={goal === g.key}
                    onClick={() => setGoal(g.key)}>{g.label}</button>
          ))}
        </div>
      </div>

      <div>
        <div className="label">Тижневий бюджет</div>
        <div className="card">
          <div className="row" style={{ borderTop: 'none', marginTop: 0, paddingTop: 0 }}>
            <span className="k">Ліміт на тиждень</span>
            <span className="budget-value">{budget.toLocaleString('uk-UA')} ₴</span>
          </div>
          <input className="slider" type="range" min="300" max="4000" step="100"
                 value={budget} onChange={(e) => setBudget(Number(e.target.value))}
                 aria-label="Тижневий бюджет" />
        </div>
      </div>

      <div>
        <div className="label">Обмеження в харчуванні</div>
        <div className="pills">
          {DIETS.map((d) => (
            <button key={d.key} className="pill"
                    aria-pressed={d.key === 'none' ? diets.length === 0 : diets.includes(d.key)}
                    onClick={() => toggleDiet(d.key)}>{d.label}</button>
          ))}
        </div>
        <p className="muted" style={{ marginTop: 10 }}>
          Обмеження з вашого профілю Сільпо агент враховує автоматично.
        </p>
      </div>

      <div>
        <div className="label">Людей у домі</div>
        <div className="pills">
          {[1, 2, 3, 4].map((n) => (
            <button key={n} className="pill" aria-pressed={household === n}
                    onClick={() => setHousehold(n)}>{n}</button>
          ))}
        </div>
      </div>
    </Screen>
  )
}
