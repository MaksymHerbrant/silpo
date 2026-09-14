import { useCallback, useEffect, useState } from 'react'
import AddToCartButton from '../components/AddToCartButton'
import Screen from '../components/Screen'
import Thumb from '../components/Thumb'
import Icon from '../components/Icon'
import { api } from '../lib/api'

/**
 * Акції та нагадування.
 *
 * Усе тут уже профільтровано ціновим порогом гостя. Дельта завжди в гривнях,
 * не у відсотках: «−18 ₴» читається миттєво, «−12%» треба рахувати.
 *
 * Цикл поповнення береться з реальних дат покупок (медіана проміжків), а не з
 * припущення за категорією — тому в рядку прямо написано, звідки він узявся.
 */
function whenLabel(row) {
  if (row.overdue) return `мало закінчитись ${Math.abs(row.due_in_days)} дн. тому`
  if (row.due_in_days === 0) return 'за розрахунком закінчується сьогодні'
  if (row.due_in_days === 1) return 'закінчується завтра'
  return `приблизно через ${row.due_in_days} дн.`
}

export default function Promotions({ plan, onOpenItem, onOpenSettings }) {
  const [reminders, setReminders] = useState(null)
  const [drops, setDrops] = useState(null)
  const [coupons, setCoupons] = useState(null)
  const [pending, setPending] = useState({})

  const ready = plan?.has_data && !plan?.building

  const load = useCallback(async () => {
    if (!ready) return
    try { setReminders(await api.reminders()) } catch { /* не критично */ }
    try { setDrops(await api.priceDrops()) } catch { /* не критично */ }
    try { setCoupons(await api.coupons()) } catch { /* не критично */ }
  }, [ready])

  useEffect(() => { load() }, [load])

  async function toggle(slug, enabled) {
    setPending((p) => ({ ...p, [slug]: true }))
    try {
      setReminders(await api.setReminder(slug, { enabled }))
    } finally {
      setPending((p) => { const n = { ...p }; delete n[slug]; return n })
    }
  }

  if (!plan?.has_data) {
    return (
      <Screen title="Вигода" tabs>
        <div className="center">
          {plan?.building
            ? <><div className="spinner" />Читаю ваші чеки й акції…</>
            : (plan?.reason || 'Даних поки немає')}
        </div>
      </Screen>
    )
  }

  const items = plan.items || []
  const summary = plan.summary || {}
  const promos = items.filter((i) => i.on_promotion && i.saved > 0)
  const swaps = items.filter((i) => i.alternative && i.action !== 'blocked')
  const due = reminders?.due || []
  const upcoming = reminders?.upcoming || []
  const priceDrops = drops?.drops || []

  return (
    <Screen title="Вигода" tabs>
      <div>
        <h1>Вигода на звичному</h1>
        <p className="lede">
          З ваших {summary.receipts} чеків. Заміни підбирались із порогом «{summary.price_tolerance_label}».
        </p>
      </div>

      {priceDrops.length > 0 && (
        <div className="card">
          <div className="section-row">
            <h3>Подешевшало</h3>
            <span className="v money">{Math.round(drops.total_saved)} ₴</span>
          </div>
          {priceDrops.map((d) => (
            <div className="offer" key={d.slug}>
              <Thumb src={d.image} />
              <button className="offer-body" onClick={() => onOpenItem(d.slug)}>
                <span className="offer-name">{d.name}</span>
                <span className="plan-meta">
                  <span>{Math.round(d.price)} ₴</span>
                  <s>{Math.round(d.was)} ₴</s>
                  <span className="delta down">{Math.round(d.saved)} ₴</span>
                  {d.lowest_seen && <span>· найнижча за час стеження</span>}
                </span>
              </button>
              <AddToCartButton item={d} source="promo" />
            </div>
          ))}
        </div>
      )}

      {drops?.first_run && priceDrops.length === 0 && (
        <div className="card plain">
          <p className="muted">
            Запам'ятали ціни {drops.tracked} ваших регулярних товарів. Щойно щось
            подешевшає — покажемо тут різницю.
          </p>
        </div>
      )}

      {(coupons?.coupons || []).length > 0 && (
        <div className="card">
          <div className="section-row">
            <h3>Ваші купони</h3>
            <span className="muted">{coupons.coupons.length}</span>
          </div>
          {coupons.coupons.map((c) => (
            <div className="offer" key={c.id}>
              <span className="offer-body">
                <span className="offer-name">{c.description}</span>
                <span className="plan-meta">
                  {c.reward && <span className="delta down">{c.reward}</span>}
                  {c.until && <span>· до {c.until}</span>}
                </span>
              </span>
            </div>
          ))}
          <p className="over-note">Купони видає Сільпо — активуйте їх у застосунку Сільпо.</p>
        </div>
      )}

      {promos.length > 0 && (
        <div className="card">
          <div className="section-row">
            <h3>Зараз в акції</h3>
            <span className="v money">
              {Math.round(promos.reduce((s, i) => s + i.saved * i.quantity, 0))} ₴
            </span>
          </div>
          {promos.map((i) => (
            <div className="offer" key={i.slug}>
              <Thumb src={i.image} />
              <button className="offer-body" onClick={() => onOpenItem(i.slug)}>
                <span className="offer-name">{i.name}</span>
                <span className="plan-meta">
                  <span>{Math.round(i.price)} ₴</span>
                  {i.old_price && <s>{Math.round(i.old_price)} ₴</s>}
                  <span className="delta down">{Math.round(i.saved)} ₴</span>
                </span>
              </button>
              <AddToCartButton item={i} source="promo" />
            </div>
          ))}
        </div>
      )}

      {swaps.length > 0 && (
        <div className="card">
          <div className="section-row"><h3>Вигідніші аналоги</h3></div>
          {swaps.map((i) => (
            <div className="offer" key={i.slug}>
              <Thumb src={i.alternative.image || i.image} />
              <button className="offer-body" onClick={() => onOpenItem(i.slug)}>
                <span className="offer-name">{i.alternative.name}</span>
                <span className="plan-meta"><span>замість «{i.name}»</span></span>
                <span className="plan-meta">
                  <span>{Math.round(i.alternative.price)} ₴</span>
                  {i.alternative.saved > 0 && (
                    <span className="delta down">{Math.round(i.alternative.saved)} ₴</span>
                  )}
                  <span>· {i.alternative.why}</span>
                </span>
              </button>
              <AddToCartButton
                item={{ ...i.alternative, quantity: i.quantity }}
                source="promo"
              />
            </div>
          ))}
        </div>
      )}

      {due.length > 0 && (
        <div className="card">
          <div className="section-row">
            <h3>Час поповнити</h3>
            <span className="muted">{Math.round(reminders.summary.due_total)} ₴</span>
          </div>
          {due.map((r) => (
            <div className="due-row" key={r.slug}>
              <Thumb src={r.image} />
              <button className="due-body" onClick={() => onOpenItem(r.slug)}>
                <div className="due-name">{r.name}</div>
                <div className={`due-when${r.overdue ? ' overdue' : ''}`}>
                  {whenLabel(r)} · раз на {r.cycle_days} дн.
                </div>
                <button
                  className={`bell${r.reminder_on ? ' on' : ''}`}
                  disabled={Boolean(pending[r.slug])}
                  onClick={(e) => { e.stopPropagation(); toggle(r.slug, !r.reminder_on) }}
                >
                  <Icon name={r.reminder_on ? 'bell' : 'bellOff'} size={16} />{r.reminder_on ? 'нагадування увімкнено' : 'нагадати, коли закінчиться'}
                </button>
              </button>
              <AddToCartButton item={r} source="promo" />
            </div>
          ))}
          <p className="over-note">
            Ритм порахований із ваших чеків. «+» кладе в кошик, дзвіночок — нагадування в боті.
          </p>
        </div>
      )}

      {upcoming.length > 0 && (
        <div className="card plain">
          <div className="section-row"><h3>Найближчим часом</h3></div>
          {upcoming.map((r) => (
            <div className="due-row" key={r.slug}>
              <button className="due-body" onClick={() => onOpenItem(r.slug)}>
                <div className="due-name">{r.name}</div>
                <div className="due-when">{whenLabel(r)} · раз на {r.cycle_days} дн.</div>
              </button>
              <button
                className={`bell${r.reminder_on ? ' on' : ''}`}
                disabled={Boolean(pending[r.slug])}
                onClick={() => toggle(r.slug, !r.reminder_on)}
              >
                <Icon name={r.reminder_on ? 'bell' : 'bellOff'} size={18} />
              </button>
            </div>
          ))}
        </div>
      )}

      {!promos.length && !swaps.length && !due.length && !priceDrops.length && (
        <div className="card plain">
          <p className="muted">
            Жоден із {summary.items} товарів вашого набору зараз не в акції, і
            персональних промо від Сільпо теж немає. Щойно щось подешевшає — зʼявиться тут.{' '}
            <button className="inline-link" onClick={onOpenSettings}>Змінити ціновий поріг</button>.
          </p>
        </div>
      )}
    </Screen>
  )
}
