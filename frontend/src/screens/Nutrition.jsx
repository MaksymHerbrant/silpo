import { useEffect, useState } from 'react'
import AddToCartButton from '../components/AddToCartButton'
import Screen from '../components/Screen'
import Thumb from '../components/Thumb'
import { api } from '../lib/api'

/**
 * Харчування — свідомо БЕЗ бала як героя.
 *
 * Ми бачимо покупки, а не раціон: людина їсть у гостях, на роботі, готує із
 * запасів. Заявляти «ваше харчування на 8 з 10» на таких даних — обіцянка,
 * яку не можна захистити.
 *
 * Тому головне тут — ОДНЕ конкретне спостереження, привʼязане до реальної
 * покупки, з альтернативою й вибором. Бал лишився, але як довідка в розгортці
 * і з чесним підписом, що це структура ВИТРАТ, а не оцінка раціону.
 */
const PERIODS = [
  { key: 'week', label: 'Тиждень' },
  { key: 'month', label: 'Місяць' },
  { key: 'all', label: 'Весь час' },
]

export default function Nutrition({ plan, onOpenItem, onSwitch, chosen }) {
  const depth = plan?.summary?.nutrition_depth ?? 1
  const [period, setPeriod] = useState('month')
  const [data, setData] = useState(null)
  const [deep, setDeep] = useState(depth >= 2)
  const [narrow, setNarrow] = useState(false)

  useEffect(() => {
    let alive = true
    let timer = null
    const tick = async () => {
      try {
        const res = await api.nutrition(period)
        if (!alive) return
        setData(res)
        if (!res.building) clearInterval(timer)
      } catch { clearInterval(timer) }
    }
    setData(null)
    tick()
    timer = setInterval(tick, 2500)
    return () => { alive = false; clearInterval(timer) }
  }, [period])

  // Одне спостереження — з плану, привʼязане до реальної покупки
  const health = (plan?.findings || []).find((f) => f.kind === 'health')
  const observed = (plan?.items || []).find(
    (i) => health?.slugs?.includes(i.slug) && i.alternative,
  )

  if (!data || data.building || !data.has_data) {
    return (
      <Screen title="Харчування" tabs>
        <div className="center">
          {!data || data.building
            ? <><div className="spinner" />Дивлюсь на структуру ваших покупок…</>
            : (data.reason || 'Даних поки немає')}
        </div>
      </Screen>
    )
  }

  const { score, sentence, plate, macros, narrow: narrowData } = data
  const recs = data.recommendations || []
  const above = plate.shares.filter((s) => s.status === 'above')
  const useAlt = observed ? chosen?.[observed.slug]?.useAlternative : false

  return (
    <Screen title="Харчування" tabs>
      <div>
        <h1>Одне спостереження</h1>
        <p className="lede">
          Це видно з ваших покупок — не з того, що ви справді їсте. Тому тут не
          оцінка раціону, а одна конкретна річ, яку варто помітити.
        </p>
      </div>

      {/* --- головне: одне спостереження з вибором --- */}
      {observed ? (
        <div className="card">
          <div className="obs-name">{observed.name}</div>
          <p className="obs-why">{health.detail}</p>
          <div className="obs-alt">
            <div className="obs-alt-row">
              <span>{observed.alternative.name}</span>
              <span className="obs-price">{Math.round(observed.alternative.price)} ₴</span>
            </div>
            <p className="muted" style={{ marginTop: 4 }}>
              {observed.alternative.why}
              {observed.alternative.saved > 0 &&
                <b className="money"> · {Math.round(observed.alternative.saved)} ₴ дешевше</b>}
            </p>
            {observed.alternative.composition_known === false && (
              <p className="over-note" style={{ color: 'var(--money)', fontWeight: 600 }}>
                Каталог не публікує склад цієї заміни — прочитайте на упаковці.
              </p>
            )}
          </div>
          <div className="obs-actions">
            <button
              className={`btn ${useAlt ? 'ghost' : ''}`}
              onClick={() => useAlt && onSwitch?.(observed.slug)}
            >
              Лишити своє
            </button>
            <button
              className={`btn ${useAlt ? '' : 'ghost'}`}
              onClick={() => !useAlt && onSwitch?.(observed.slug)}
            >
              Взяти заміну
            </button>
          </div>
          <button className="why" onClick={() => onOpenItem(observed.slug)}>
            Чому саме це →
          </button>
        </div>
      ) : (
        <div className="card plain">
          <p className="muted">
            Надійного спостереження поки немає: каталог «Сільпо» здебільшого не
            публікує склад товарів, а на здогадках тут нічого не будується.
          </p>
        </div>
      )}

      {/* --- що варто додати: товари підібрані моделлю --- */}
      {recs.length > 0 && (
        <div className="card">
          <div className="section-row"><h3>Що варто додати</h3></div>
          {recs.map((r) => (
            <div key={r.key} className="rec">
              <div className="rec-head">
                {r.advice || `Більше «${r.label.toLowerCase()}» у кошику`}
              </div>
              {r.note && <p className="over-note">{r.note}</p>}
              {(r.products || []).map((prod) => (
                <div className="offer" key={prod.slug}>
                  <Thumb src={prod.image} />
                  <span className="offer-body">
                    <span className="offer-name">{prod.name}</span>
                    <span className="plan-meta">
                      <span>{Math.round(prod.price)} ₴</span>
                      {prod.on_promotion && (
                        <span className="delta down">{Math.round(prod.old_price - prod.price)} ₴</span>
                      )}
                      {prod.composition_known === false && <span>· склад не вказано</span>}
                    </span>
                  </span>
                  <AddToCartButton item={prod} source="nutrition" />
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* --- довідка: структура витрат, чесно підписана --- */}
      <div className="card plain">
        <button className="disclose" onClick={() => setDeep((v) => !v)}>
          <span>Структура витрат на їжу</span>
          <span className="chev">{deep ? '−' : '+'}</span>
        </button>
        {deep && (
          <>
            <p className="over-note" style={{ marginTop: 8 }}>
              <b>Це не оцінка вашого раціону.</b> Це наскільки розподіл ВИТРАТ на
              їжу близький до орієнтирів Гарвардської тарілки — {score} з 10.
              Орієнтири є евристикою, а не медичною нормою.
            </p>
            <p className="muted" style={{ marginTop: 6 }}>{sentence}</p>

            {above.length > 0 && above.slice(0, 3).map((s) => (
              <div className="bar-item" key={s.key} style={{ marginTop: 10 }}>
                <div className="bar-head">
                  <span>{s.label}</span>
                  <span className="amt">{s.share}% · орієнтир до {Math.round(s.target_max)}%</span>
                </div>
                <div className="bar-track">
                  <i className="warn" style={{ width: `${Math.min(s.share, 100)}%` }} />
                </div>
              </div>
            ))}

            {macros.covered > 0 ? (
              <>
                <h4 className="sub-head">БЖВ звичного набору · на 100 г</h4>
                <div className="kv"><span className="k">Калорійність</span><span className="v">{macros.per_100g.kcal} ккал</span></div>
                <div className="kv"><span className="k">Білки</span><span className="v">{macros.per_100g.protein} г</span></div>
                <div className="kv"><span className="k">Жири</span><span className="v">{macros.per_100g.fat} г</span></div>
                <div className="kv"><span className="k">Вуглеводи</span><span className="v">{macros.per_100g.carbs} г</span></div>
                <p className="over-note">
                  Порахував по {macros.covered} з {macros.total} позицій ({macros.coverage_pct}% покриття).
                  Товари без харчової цінності в розрахунок не входять — нулі замість них не підставляю.
                  {!macros.enough_for_daily && ' Денні норми не показую: покриття замале.'}
                </p>
              </>
            ) : (
              <p className="over-note">
                БЖВ порахувати нема з чого — каталог не віддав харчової цінності
                для товарів вашого набору.
              </p>
            )}
          </>
        )}
      </div>

      <div className="card plain">
        <button className="disclose" onClick={() => setNarrow((v) => !v)}>
          <span>Цукор і сіль</span>
          <span className="chev">{narrow ? '−' : '+'}</span>
        </button>
        {narrow && (
          (narrowData.sugar.length === 0 && narrowData.salt.length === 0) ? (
            <p className="over-note">
              Каталог «Сільпо» не публікує вміст цукру й солі для ваших товарів —
              тому тут поки порожньо.
            </p>
          ) : (
            <>
              {[...narrowData.sugar, ...narrowData.salt].map((n, i) => (
                <div className="kv" key={i}>
                  <span className="k">{n.name}</span>
                  <span className="v">{n.per_100g} г / 100 г</span>
                </div>
              ))}
            </>
          )
        )}
      </div>

      <div className="pills" style={{ justifyContent: 'center' }}>
        {PERIODS.map((p) => (
          <button key={p.key} className="pill" aria-pressed={period === p.key}
                  onClick={() => setPeriod(p.key)}>{p.label}</button>
        ))}
      </div>
    </Screen>
  )
}
