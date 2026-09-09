import { useCallback, useEffect, useState } from 'react'
import Nav from './components/Nav'
import { api, login } from './lib/api'
import { initTelegram, notify, WebApp } from './lib/telegram'
import Allergens from './screens/Allergens'
import DebugLog from './screens/DebugLog'
import Home from './screens/Home'
import Onboarding from './screens/Onboarding'
import Swaps from './screens/Swaps'
import Profile from './screens/Profile'

function Loading({ text = 'Аналізуємо кошик…' }) {
  return (
    <div className="center">
      <div className="spinner" />
      {text}
    </div>
  )
}

export default function App() {
  const [state, setState] = useState({ status: 'boot' })
  const [tab, setTab] = useState('profile')
  const [analysis, setAnalysis] = useState(null)
  const [trend, setTrend] = useState(null)
  const [swaps, setSwaps] = useState(null)
  const [allergens, setAllergens] = useState(null)
  const [log, setLog] = useState(null)
  const [tools, setTools] = useState(null)
  const [selectedSwap, setSelectedSwap] = useState(null)
  const [applying, setApplying] = useState(false)
  const [sendingReport, setSendingReport] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => { initTelegram() }, [])

  const boot = useCallback(async () => {
    try {
      const session = await login()
      setState({
        status: session.silpo_connected ? 'ready' : 'onboarding',
        user: session.user,
      })
    } catch (e) {
      setState({ status: 'error', message: e.message })
    }
  }, [])

  useEffect(() => { boot() }, [boot])

  const loadAnalysis = useCallback(async () => {
    setBusy(true)
    try {
      setAnalysis(await api.cartAnalysis())
    } catch (e) {
      if (e.status === 409) setState((s) => ({ ...s, status: 'onboarding' }))
      else setAnalysis({ empty: true, reason: `Не вдалось прочитати кошик: ${e.message}`, items: [] })
    } finally {
      setBusy(false)
    }
  }, [])

  // Профіль — головний екран, тому вантажимо його одразу після логіну,
  // а кошик підвантажуємо тихо у фоні (він потрібен і для бейджа в навігації).
  useEffect(() => {
    if (state.status !== 'ready') return
    if (!trend) {
      api.trends(false)
        .then((data) => {
          setTrend(data)
          // Кеш порожній після рестарту бекенду — добудовуємо у фоні
          if (data?.needs_refresh || data?.building) rebuildTrend(true)
        })
        .catch((e) => setTrend({ weeks: [], reason: e.message }))
    }
    if (!analysis) loadAnalysis()
  }, [state.status])

  useEffect(() => {
    if (state.status !== 'ready') return
    if (tab === 'swaps' && !swaps) api.swaps(true).then(setSwaps).catch(() => setSwaps({ suggestions: [] }))
    if (tab === 'allergens' && !allergens) api.allergens().then(setAllergens).catch(() => setAllergens(null))
    if (tab === 'debug') api.mcpLog(50).then(setLog).catch(() => {})
  }, [tab, state.status, swaps, allergens])

  async function applySwap(id) {
    setApplying(true)
    try {
      await api.applySwap(id)
      notify('success')
      WebApp.showPopup?.({
        title: 'Готово',
        message: 'Товар замінено у твоєму кошику Сільпо.',
        buttons: [{ type: 'ok' }],
      })
      setSelectedSwap(null)
      setSwaps(null)
      setAnalysis(null)
      setSwaps(await api.swaps(true))
    } catch (e) {
      notify('error')
      WebApp.showAlert?.(`Не вдалось застосувати заміну: ${e.message}`)
    } finally {
      setApplying(false)
    }
  }

  /**
   * Профіль будується у фоні на бекенді (до хвилини), тому тут ми лише
   * запускаємо його й опитуємо статус. Довгі HTTP-запити через тунель
   * рвались із 502 — саме тому не чекаємо відповіді синхронно.
   */
  async function rebuildTrend(silent = false) {
    if (!silent) setTrend(null)
    setRebuilding(true)
    try {
      await api.rebuildTrends()
      for (let i = 0; i < 40; i += 1) {
        await new Promise((r) => setTimeout(r, 3000))
        const data = await api.trends(false).catch(() => null)
        if (!data) continue
        if (!data.building) {
          setTrend(data)
          return
        }
        if (data.weeks?.length) setTrend(data)   // показуємо часткові дані одразу
      }
    } catch (e) {
      setTrend((prev) => prev || { weeks: [], reason: e.message })
    } finally {
      setRebuilding(false)
    }
  }

  async function sendReport() {
    setSendingReport(true)
    try {
      await api.sendReport()
      notify('success')
      WebApp.showPopup?.({
        title: 'Звіт надіслано',
        message: 'Подивіться повідомлення від бота — там аналіз кошика і пропозиція заміни.',
        buttons: [{ type: 'ok' }],
      })
    } catch (e) {
      notify('error')
      WebApp.showAlert?.(`Не вдалось надіслати: ${e.message}`)
    } finally {
      setSendingReport(false)
    }
  }

  async function declineSwap(id) {
    await api.declineSwap(id)
    setSwaps((s) => ({ ...s, suggestions: s.suggestions.filter((x) => x.id !== id) }))
  }

  if (state.status === 'boot') return <Loading text="Вмикаємось…" />
  if (state.status === 'error') {
    return (
      <div className="screen">
        <div className="card center">
          <p>Щось пішло не так</p>
          <p className="muted">{state.message}</p>
          <button className="btn secondary" style={{ marginTop: 14 }} onClick={boot}>
            Спробувати ще раз
          </button>
        </div>
      </div>
    )
  }
  if (state.status === 'onboarding') {
    return <Onboarding user={state.user} onConnected={boot} />
  }

  return (
    <>
      {tab === 'profile' && (
        <Profile
          trend={trend}
          cart={analysis}
          loading={!trend || rebuilding}
          onRefresh={() => rebuildTrend()}
          onOpenCart={() => setTab('cart')}
          onSendReport={sendReport}
          sending={sendingReport}
        />
      )}
      {tab === 'cart' &&
        (analysis
          ? <Home analysis={analysis} onRefresh={() => { setAnalysis(null); loadAnalysis() }}
                  onSendReport={sendReport} sending={sendingReport} />
          : <Loading />)}
      {tab === 'swaps' &&
        (swaps ? (
          <Swaps
            swaps={swaps.suggestions}
            stats={swaps.stats}
            selected={selectedSwap}
            onSelect={setSelectedSwap}
            onApply={applySwap}
            onDecline={declineSwap}
            applying={applying}
          />
        ) : (
          <Loading text="Шукаємо здоровіші аналоги…" />
        ))}
      {tab === 'allergens' &&
        (allergens ? <Allergens data={allergens} /> : <Loading text="Звіряємо склад…" />)}
      {tab === 'debug' && (
        <DebugLog
          log={log}
          tools={tools}
          onRefresh={() => api.mcpLog(50).then(setLog)}
          onLoadTools={() => api.mcpTools().then(setTools)}
        />
      )}
      {busy && tab !== 'home' && null}
      <Nav tab={tab} onChange={setTab} cartCount={analysis && !analysis.empty ? analysis.items?.length : 0} />
    </>
  )
}
