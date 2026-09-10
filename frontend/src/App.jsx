import { useCallback, useEffect, useRef, useState } from 'react'
import { api, login } from './lib/api'
import { initTelegram, notify, WebApp } from './lib/telegram'
import Checkout from './screens/Checkout'
import Done from './screens/Done'
import CardDetail from './screens/CardDetail'
import Dashboard from './screens/Dashboard'
import ItemDetail from './screens/ItemDetail'
import Insights from './screens/Insights'
import ShoppingPlan from './screens/ShoppingPlan'
import SilpoConnect from './screens/SilpoConnect'

/**
 * Потік без опитувань: гість заходить — і одразу бачить знахідки.
 * Історія покупок → знахідки → план → дія (кошик або список).
 */
export default function App() {
  const [state, setState] = useState({ status: 'boot' })
  const [screen, setScreen] = useState('home')
  const [plan, setPlan] = useState(null)
  const [insights, setInsights] = useState(null)
  const [chosen, setChosen] = useState({})
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const [sheet, setSheet] = useState(null)   // {type:'card'|'item', key}
  const poll = useRef(null)

  useEffect(() => { initTelegram() }, [])
  useEffect(() => () => clearInterval(poll.current), [])

  /** План будується у фоні до хвилини — опитуємо, поки building=true. */
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
                // Заблоковану позицію одразу показуємо з безпечною заміною
                useAlternative: i.action === 'blocked' && Boolean(i.alternative),
              },
            ]),
          ))
        }
      } catch (e) {
        // Мережа моргнула — пробуємо ще. Але не вічно.
        if (tries > 40) {
          clearInterval(poll.current)
          setPlan({ has_data: false, reason: e.message })
        }
      }
    }
    tick()
    poll.current = setInterval(tick, 2500)
  }, [])

  const boot = useCallback(async () => {
    try {
      const session = await login()
      if (!session.silpo_connected) {
        setState({ status: 'connect', user: session.user })
        return
      }
      setState({ status: 'ready', user: session.user })
      loadPlan()
      api.insights().then(setInsights).catch(() => {})
    } catch (e) {
      setState({ status: 'error', message: e.message })
    }
  }, [loadPlan])

  useEffect(() => { boot() }, [boot])

  const selectedItems = (plan?.items || [])
    .filter((i) => chosen[i.slug]?.selected)
    .map((i) => {
      const alt = chosen[i.slug]?.useAlternative ? i.alternative : null
      return {
        product_id: alt ? alt.product_id : i.product_id,
        quantity: i.quantity,
        name: alt ? alt.name : i.name,
      }
    })

  const selectedTotal = (plan?.items || [])
    .filter((i) => chosen[i.slug]?.selected)
    .reduce((sum, i) => {
      const alt = chosen[i.slug]?.useAlternative ? i.alternative : null
      return sum + (alt ? alt.price : i.price) * i.quantity
    }, 0)

  async function toCart() {
    setBusy(true)
    try {
      const result = await api.planToCart(selectedItems)
      notify('success')
      setDone({ mode: 'cart', result })
      setScreen('done')
    } catch (e) {
      notify('error')
      WebApp.showAlert?.(`Не вдалось створити кошик: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function toList() {
    setBusy(true)
    try {
      const list = await api.planToList(selectedItems)
      setDone({ mode: 'list', list })
      setScreen('done')
    } catch (e) {
      WebApp.showAlert?.(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (state.status === 'boot') return <div className="center"><div className="spinner" />Вмикаємось…</div>
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

  if (screen === 'insights') return <Insights data={insights} onBack={() => setScreen('home')} />

  const openItemFromPlan = (slug) => setSheet({ type: 'item', key: slug })

  if (screen === 'plan') {
    return (
      <>
      <ShoppingPlan
        plan={plan}
        chosen={chosen}
        onToggle={(slug) => setChosen((c) => ({
          ...c, [slug]: { ...c[slug], selected: !c[slug]?.selected },
        }))}
        onSwitch={(slug) => setChosen((c) => ({
          ...c, [slug]: { ...c[slug], useAlternative: !c[slug]?.useAlternative },
        }))}
        onOpenItem={openItemFromPlan}
        onBack={() => setScreen('home')}
        onNext={() => setScreen('checkout')}
      />
      {sheet?.type === 'item' && (
        <ItemDetail
          item={(plan?.items || []).find((i) => i.slug === sheet.key)}
          chosen={chosen[sheet.key]}
          onSwitch={(slug) => setChosen((c) => ({
            ...c, [slug]: { ...c[slug], selected: true, useAlternative: !c[slug]?.useAlternative },
          }))}
          onClose={() => setSheet(null)}
        />
      )}
      </>
    )
  }

  if (screen === 'checkout') {
    return (
      <Checkout
        count={selectedItems.length}
        total={selectedTotal}
        busy={busy}
        onCart={toCart}
        onList={toList}
        onBack={() => setScreen('plan')}
      />
    )
  }

  if (screen === 'done' && done) {
    return (
      <Done
        mode={done.mode}
        result={done.result}
        list={done.list}
        onBack={() => setScreen('plan')}
        onHome={() => { setScreen('home'); loadPlan(true) }}
      />
    )
  }

  const openItem = (slug) => setSheet({ type: 'item', key: slug })
  const switchAlt = (slug) => setChosen((c) => ({
    ...c, [slug]: { ...c[slug], selected: true, useAlternative: !c[slug]?.useAlternative },
  }))

  return (
    <>
      <Dashboard
        plan={plan}
        building={plan?.building}
        onOpenCard={(kind) => setSheet({ type: 'card', key: kind })}
        onOpenItem={openItem}
        onOpenPlan={() => setScreen('plan')}
        onRefresh={() => loadPlan(true)}
      />
      {sheet?.type === 'card' && (
        <CardDetail
          kind={sheet.key}
          plan={plan}
          onClose={() => setSheet(null)}
          onOpenItem={openItem}
        />
      )}
      {sheet?.type === 'item' && (
        <ItemDetail
          item={(plan?.items || []).find((i) => i.slug === sheet.key)}
          chosen={chosen[sheet.key]}
          onSwitch={switchAlt}
          onClose={() => setSheet(null)}
        />
      )}
    </>
  )
}
