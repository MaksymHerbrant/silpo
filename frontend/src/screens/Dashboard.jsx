import { useEffect, useState } from 'react'
import Screen from '../components/Screen'
import { api } from '../lib/api'

/**
 * «Інсайти» — ДОКАЗИ під рекомендаціями, а не другий головний екран.
 *
 * Свідомо НЕ містить ні стрічки можливостей, ні прев'ю кошика: це є на
 * головній, і дубль лише розмивав обидва екрани. Тут — тільки те, що
 * відповідає на питання про гроші, ритм і те, як ми відрізняємо звичку
 * від випадковості.
 */
function ago(iso) {
  if (!iso) return null
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (!Number.isFinite(mins) || mins < 0) return null
  if (mins < 60) return `${Math.max(mins, 1)} хв тому`
  const h = Math.round(mins / 60)
  return h < 24 ? `${h} год тому` : `${Math.round(h / 24)} дн. тому`
}

export default function Dashboard({ plan, insights, onOpenInsights, onRefresh }) {
  const [metrics, setMetrics] = useState(null)
  const [how, setHow] = useState(false)

  const ready = plan?.has_data && !plan?.building
  useEffect(() => {
    if (!ready) return
    let alive = true
    api.metrics().then((m) => { if (alive) setMetrics(m) }).catch(() => {})
    return () => { alive = false }
  }, [ready])

  if (!plan?.has_data) {
    return (
      <Screen title="Інсайти" tabs>
        <div className="center">
          {plan?.building
            ? <><div className="spinner" />{plan.phase || 'Рахую…'}</>
            : (plan?.reason || 'Даних поки немає')}
        </div>
      </Screen>
    )
  }

  const { summary = {}, habit_showcase: show } = plan
  const money = insights?.money
  const top = (insights?.top_by_spend || []).slice(0, 5)
  const maxItem = Math.max(...top.map((t) => t.spend), 1)
  const rhythm = insights?.rhythm
  const weeks = rhythm?.weeks || []
  const maxWeek = Math.max(...weeks.map((w) => w.spend), 1)
  const WEEKDAYS = ['понеділок', 'вівторок', 'середу', 'четвер', 'пʼятницю', 'суботу', 'неділю']
  const proposals = metrics?.proposals

  return (
    <Screen title="Інсайти" tabs>
      <div>
        <h1>Що видно з ваших чеків</h1>
        <p className="lede">
          {summary.receipts} чеків за {Math.round(summary.based_on_weeks)} тижнів.
          На цьому тримаються всі рекомендації.
        </p>
      </div>

      {/* --- головний доказ продукту: звичка ≠ повторення --- */}
      {show?.strong && (
        <div className="card">
          <div className="section-row"><h3>Звичка — це не повторення</h3></div>

          {show.weak && (
            <div className="hab hab-weak">
              <div className="hab-name">{show.weak.name}</div>
              <div className="hab-nums">
                <span><b>{show.weak.lines}</b> рядків у чеках</span>
                <span>але лише <b>{show.weak.days}</b> {show.weak.days === 1 ? 'день' : 'дні'} покупки</span>
              </div>
              <div className="hab-verdict weak">один похід — ще не звичка</div>
            </div>
          )}

          <div className="hab hab-strong">
            <div className="hab-name">{show.strong.kind ? `${show.strong.kind} · ` : ''}{show.strong.name}</div>
            <div className="hab-nums">
              <span><b>{show.strong.days}</b> різних днів</span>
              <span><b>{show.strong.weeks}</b> різних тижнів</span>
              {show.strong.brands > 1 && <span><b>{show.strong.brands}</b> марок</span>}
            </div>
            <div className="hab-verdict strong">
              {show.strong.brand_indifferent
                ? `стабільна звичка на рівні виду — марка вам не принципова, тож є де знайти вигідніше`
                : 'стабільна звичка, і марка теж стала частиною її'}
            </div>
          </div>
        </div>
      )}

      {money && (
        <div className="card">
          <div className="section-row"><h3>Скільки коштує ваш похід</h3></div>
          <div className="stat-grid">
            <div className="stat-tile">
              <div className="n">{Math.round(money.avg_check)} ₴</div>
              <div className="t">середній чек</div>
            </div>
            <div className="stat-tile">
              <div className="n">{money.visits_per_week}</div>
              <div className="t">походи на тиждень</div>
            </div>
            <div className="stat-tile">
              <div className="n">{Math.round(money.per_week).toLocaleString('uk-UA')} ₴</div>
              <div className="t">витрати на тиждень</div>
            </div>
            <div className="stat-tile">
              <div className="n money">{Math.round(money.total_saved).toLocaleString('uk-UA')} ₴</div>
              <div className="t">уже зекономлено на акціях</div>
            </div>
          </div>
        </div>
      )}

      {top.length > 0 && (
        <div className="card">
          <div className="section-row">
            <h3>Куди пішли гроші</h3>
            <button className="inline-link" onClick={onOpenInsights}>детально</button>
          </div>
          {top.map((t) => (
            <div className="bar-item" key={t.name}>
              <div className="bar-head">
                <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {t.name}
                </span>
                <span className="amt">{Math.round(t.spend)} ₴ · {t.share_of_spend}%</span>
              </div>
              <div className="bar-track"><i style={{ width: `${(t.spend / maxItem) * 100}%` }} /></div>
            </div>
          ))}
        </div>
      )}

      {rhythm && rhythm.active_weeks > 0 && (
        <div className="card">
          <div className="section-row"><h3>Ритм покупок</h3></div>
          <p className="muted" style={{ marginBottom: 10 }}>
            Ви заходите в Сільпо <b>{rhythm.visits_per_week}</b> рази на тиждень,
            найчастіше у <b>{WEEKDAYS[rhythm.top_weekday]}</b> ({rhythm.top_weekday_share}% походів).
            Звичайний тиждень — <b>{Math.round(rhythm.typical_spend)} ₴</b>.
          </p>
          <div className="spark">
            {weeks.map((w) => (
              <div key={w.week} className={w.visits ? '' : 'empty'} title={`${w.week}: ${Math.round(w.spend)} ₴, ${w.visits} походів`}>
                <i style={{ height: `${Math.max((w.spend / maxWeek) * 100, w.visits ? 4 : 0)}%` }} />
                <span className="spark-val">{w.visits ? Math.round(w.spend) : '—'}</span>
              </div>
            ))}
          </div>
          <div className="spark-labels">
            {weeks.map((w) => <span key={w.week}>{w.week.slice(8)}.{w.week.slice(5, 7)}</span>)}
          </div>
          <p className="over-note">
            Останні 12 тижнів, ₴ за тиждень. Порожній стовпчик — тиждень без чека
            {rhythm.active_weeks < 12 && ` (таких ${12 - rhythm.active_weeks})`}.
          </p>
        </div>
      )}

      {proposals?.shown > 0 && (
        <div className="card plain">
          <div className="section-row"><h3>Прийняті пропозиції</h3></div>
          {proposals.decided === 0 ? (
            <p className="muted">
              {proposals.shown} пропозицій показано. Після першого прийнятого
              рішення тут зʼявиться відсоток і сума.
            </p>
          ) : (
            <>
              <div className="kv">
                <span className="k">Прийнято</span>
                <span className="v">
                  {proposals.accepted} з {proposals.decided}
                  {proposals.rate != null && ` · ${proposals.rate}%`}
                </span>
              </div>
              {proposals.saved > 0 && (
                <div className="kv">
                  <span className="k">Зекономлено на прийнятому</span>
                  <span className="v money">{Math.round(proposals.saved)} ₴</span>
                </div>
              )}
              {!proposals.reliable && (
                <p className="over-note">Рішень поки мало — відсоток стане показовим після пʼяти.</p>
              )}
            </>
          )}
        </div>
      )}

      <div className="card plain">
        <button className="disclose" onClick={() => setHow((v) => !v)}>
          <span>Як це рахується</span>
          <span className="chev">{how ? '−' : '+'}</span>
        </button>
        {how && (
          <>
            <div className="kv">
              <span className="k">Відсіяно разових покупок</span>
              <span className="v">{summary.filtered_count} на {Math.round(summary.filtered_spend || 0)} ₴</span>
            </div>
            <div className="kv">
              <span className="k">Ціновий поріг замін</span>
              <span className="v">{summary.price_tolerance_label}</span>
            </div>
            {metrics?.cycles?.measurable && (
              <div className="kv">
                <span className="k">Похибка передбачення ритму</span>
                <span className="v">± {metrics.cycles.mean_error_days} дн.</span>
              </div>
            )}
            <p className="over-note">
              <b>Це рахунок за вашими чеками, не передбачення.</b> Товар потрапляє
              в ядро, якщо ви брали його щонайменше двічі в різні дні. Ритм —
              медіана проміжків. Тютюн і алкоголь у пропозиції не потрапляють.
            </p>
          </>
        )}
      </div>

      <p className="over-note" style={{ textAlign: 'center' }}>
        Оновлено {ago(plan.built_at) || 'щойно'} ·{' '}
        <button className="inline-link" onClick={onRefresh}>оновити</button>
      </p>
    </Screen>
  )
}
