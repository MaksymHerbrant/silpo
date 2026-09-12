import { useCallback, useEffect, useRef, useState } from 'react'
import { api, login } from './lib/api'
import { CartProvider, useCart } from './lib/cart'
import { initTelegram, notify, WebApp } from './lib/telegram'
import TabBar from './components/TabBar'
import Onboarding from './onboarding/Onboarding'
import CardDetail from './screens/CardDetail'
import Cart from './screens/Cart'
import Dashboard from './screens/Dashboard'
import Home from './screens/Home'
import LiveData from './screens/LiveData'
import Done from './screens/Done'
import Insights from './screens/Insights'
import ItemDetail from './screens/ItemDetail'
import Nutrition from './screens/Nutrition'
import Promotions from './screens/Promotions'
import Settings from './screens/Settings'
import ShoppingPlan from './screens/ShoppingPlan'
import SilpoConnect from './screens/SilpoConnect'

/** Зовнішня оболонка: лише сесія і підключення Сільпо. */
export default function App() {
  const [state, setState] = useState({ status: 'boot' })

  useEffect(() => { initTelegram() }, [])

  const boot = useCallback(async () => {
    try {
      const session = await login()
      setState({
        status: session.silpo_connected ? 'ready' : 'connect',
        user: session.user,
      })
    } catch (e) {
      setState({ status: 'error', message: e.message })
    }
  }, [])

  useEffect(() => { boot() }, [boot])

  if (state.status === 'boot') {
    return <div className="center"><div className="spinner" />Вмикаємось…</div>
  }
  if (state.status === 'error') {
    return (
      <div className="center">
        <p style={{ color: 'var(--ink)' }}>Щось пішло не так</p>
        <p className="muted" style={{ marginTop: 8 }}>{state.message}</p>
        <button className="btn ghost" style={{ marginTop: 18, maxWidth: 240 }} onClick={boot}>
          Спробувати ще раз
        </button>
      </div>
    )
  }
  if (state.status === 'connect') return <SilpoConnect user={state.user} onConnected={boot} />

  return (
    <CartProvider>
      <Main user={state.user} />
    </CartProvider>
  )
}

/**
 * Застосунок: п'ять табів плюс екрани-надбудови.
 * Кошик спільний — товар із будь-якого таба лягає в один список.
 */
function Main({ user }) {
  const [tab, setTab] = useState('home')
  const [over, setOver] = useState(null)   // 'plan' | 'insights' | 'live' | 'done'
  const [plan, setPlan] = useState(null)
  const [insights, setInsights] = useState(null)
  const [settings, setSettings] = useState(null)
  const [chosen, setChosen] = useState({})
  const [sheet, setSheet] = useState(null)        // {type:'card'|'item', key}
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const poll = useRef(null)
  const { cart, add, setCart, reload } = useCart()

  useEffect(() => () => clearInterval(poll.current), [])

  /**
   * Збережений план приходить одразу — опитуємо, ЛИШЕ поки він будується.
   * Просто відкрити застосунок більше не означає перечитати всі чеки:
   * перебудова відбувається за тапом «оновити» або коли зʼявився новий чек.
   */
  const loadPlan = useCallback((refresh = false) => {
    clearInterval(poll.current)
    let tries = 0
    const tick = async () => {
      try {
        const data = await api.plan(refresh && tries === 0)
        tries += 1
        setPlan(data)
        if (!data.building) {
          clearInterval(poll.current)
          setChosen(Object.fromEntries(
            (data.items || []).map((i) => [
              i.slug,
              {
                selected: i.selected,
                useAlternative: i.action === 'blocked' && Boolean(i.alternative),
              },
            ]),
          ))
        }
      } catch (e) {
        if (tries > 40) {
          clearInterval(poll.current)
          setPlan({ has_data: false, reason: e.message })
        }
      }
    }
    tick()
    poll.current = setInterval(tick, 2500)
  }, [])

  useEffect(() => {
    api.settings().then(setSettings).catch(() => setSettings({ onboarded: true }))
  }, [])

  // Дані вантажимо лише після онбордингу — інакше гість чекає намарно
  useEffect(() => {
    if (!settings?.onboarded) return
    loadPlan()
    // Інсайти будуються у фоні — опитуємо, поки не готові, інакше блок
    // «ритм по тижнях» лишається порожнім до наступного відкриття
    let tries = 0
    const poll = async () => {
      try {
        const data = await api.insights()
        setInsights(data)
        if (data.building && tries++ < 40) setTimeout(poll, 3000)
      } catch { /* покажемо без інсайтів */ }
    }
    poll()
  }, [settings?.onboarded, loadPlan])

  async function saveSettings(values) {
    setBusy(true)
    try {
      const saved = await api.saveSettings(values)
      setSettings(saved)
      loadPlan(true)
    } catch (e) {
      WebApp.showAlert?.(`Не вдалось зберегти: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  /**
   * Обране в списку плану переїздить у спільний кошик — і гість бачить його в табі.
   *
   * Тут же фіксуються рішення щодо пропозицій: узяв заміну чи акцію —
   * прийнято; лишив своє при наявній заміні або зняв галочку з акції —
   * відхилено. Раніше записувалось лише «+» на картці, і метрика бачила
   * одне рішення на десяток показаних.
   */
  async function planToCart() {
    const items = plan?.items || []
    const picked = items.filter((i) => chosen[i.slug]?.selected)
    if (!picked.length) return
    setBusy(true)
    try {
      const rejected = []
      for (const i of items) {
        if (!i.decision_id) continue
        const state = chosen[i.slug] || {}
        const accepted = i.alternative
          ? Boolean(state.selected && state.useAlternative)
          : Boolean(state.selected)
        if (!accepted) rejected.push(i.decision_id)
      }
      for (const i of picked) {
        const alt = chosen[i.slug]?.useAlternative ? i.alternative : null
        const accepted = i.decision_id && (alt || !i.alternative)
        await add({
          product_id: alt ? alt.product_id : i.product_id,
          slug: alt ? alt.slug : i.slug,
          name: alt ? alt.name : i.name,
          image: alt ? alt.image : i.image,
          price: alt ? alt.price : i.price,
          quantity: i.quantity,
          source: 'plan',
          ...(accepted ? { decision_id: i.decision_id } : {}),
        })
      }
      await Promise.allSettled(rejected.map((id) => api.decide(id, false)))
      notify('success')
      setOver(null)
      setTab('cart')
    } catch (e) {
      WebApp.showAlert?.(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function checkout() {
    setBusy(true)
    try {
      const result = await api.cartCheckout()
      setCart({ items: [], count: 0, positions: 0, total: 0 })
      notify('success')
      setDone({ mode: 'cart', result })
      setOver('done')
    } catch (e) {
      notify('error')
      WebApp.showAlert?.(`Не вдалось надіслати кошик: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function toList() {
    setBusy(true)
    try {
      const list = await api.planToList(cart.items.map((i) => ({
        product_id: i.product_id, quantity: i.quantity, name: i.name,
      })))
      setDone({ mode: 'list', list })
      setOver('done')
    } catch (e) {
      WebApp.showAlert?.(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    setBusy(true)
    try {
      await api.logout()
      window.location.reload()
    } catch (e) {
      WebApp.showAlert?.(e.message)
    } finally {
      setBusy(false)
    }
  }

  const openItem = (slug) => setSheet({ type: 'item', key: slug })
  const openSettings = () => { setOver(null); setTab('settings') }
  const switchAlt = (slug) => setChosen((c) => ({
    ...c, [slug]: { ...c[slug], selected: true, useAlternative: !c[slug]?.useAlternative },
  }))

  const sheets = (
    <>
      {sheet?.type === 'card' && (
        <CardDetail
          kind={sheet.key} plan={plan}
          onClose={() => setSheet(null)}
          onOpenItem={openItem}
          onOpenSettings={openSettings}
          onSwitch={switchAlt}
        />
      )}
      {sheet?.type === 'item' && (
        <ItemDetail
          item={(plan?.items || []).find((i) => i.slug === sheet.key)}
          chosen={chosen[sheet.key]}
          onSwitch={switchAlt}
          onOpenSettings={() => { setSheet(null); openSettings() }}
          onClose={() => setSheet(null)}
        />
      )}
    </>
  )

  // --- онбординг: два тапи, обидва можна пропустити ---
  if (settings && !settings.onboarded) {
    return (
      <Onboarding
        settings={settings}
        name={user?.first_name}
        onDone={(values) => saveSettings(values)}
      />
    )
  }
  if (!settings) return <div className="center"><div className="spinner" />Вмикаємось…</div>

  // --- екрани-надбудови поверх табів ---
  if (over === 'done' && done) {
    return (
      <Done
        mode={done.mode} result={done.result} list={done.list}
        onBack={() => { setOver(null); setTab('cart') }}
        onHome={() => { setOver(null); setTab('analytics'); reload(); loadPlan() }}
      />
    )
  }
  if (over === 'plan') {
    return (
      <>
        <ShoppingPlan
          plan={plan} chosen={chosen}
          onToggle={(slug) => setChosen((c) => ({
            ...c, [slug]: { ...c[slug], selected: !c[slug]?.selected },
          }))}
          onSwitch={(slug) => setChosen((c) => ({
            ...c, [slug]: { ...c[slug], useAlternative: !c[slug]?.useAlternative },
          }))}
          onOpenItem={openItem}
          onOpenSettings={openSettings}
          onBack={() => setOver(null)}
          onNext={planToCart}
          busy={busy}
        />
        {sheets}
      </>
    )
  }
  if (over === 'insights') {
    return <Insights data={insights} onBack={() => setOver(null)} />
  }
  if (over === 'live') {
    return <LiveData onBack={() => setOver(null)} />
  }

  const screens = {
    home: (
      <Home
        plan={plan}
        onOpenPlan={() => setOver('plan')}
        onOpenOpportunity={(kind) => setSheet({ type: 'card', key: kind })}
        onOpenInsights={() => setTab('analytics')}
        onRefresh={() => loadPlan(true)}
      />
    ),
    nutrition: (
      <Nutrition
        plan={plan} onOpenItem={openItem}
        chosen={chosen} onSwitch={switchAlt}
      />
    ),
    promos: <Promotions plan={plan} onOpenItem={openItem} onOpenSettings={openSettings} />,
    analytics: (
      <Dashboard
        plan={plan}
        insights={insights}
        onOpenInsights={() => setOver('insights')}
        onRefresh={() => loadPlan(true)}
      />
    ),
    cart: (
      <Cart
        busy={busy}
        onCheckout={checkout}
        onList={toList}
        onOpenNutrition={() => setTab('nutrition')}
      />
    ),
    settings: (
      <Settings
        settings={settings}
        restrictions={plan?.profile?.restrictions || []}
        busy={busy}
        onSave={saveSettings}
        onLogout={logout}
        onOpenLive={() => setOver('live')}
        onOpenNutrition={() => setTab('nutrition')}
      />
    ),
  }

  return (
    <>
      {screens[tab]}
      <TabBar active={tab} onChange={(t) => { setSheet(null); setTab(t) }} />
      {sheets}
    </>
  )
}
