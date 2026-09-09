import { useCallback, useEffect, useRef, useState } from 'react'
import { api, login } from './lib/api'
import { initTelegram, notify, WebApp } from './lib/telegram'
import AgentRun from './screens/AgentRun'
import AgentStart from './screens/AgentStart'
import Basket from './screens/Basket'
import ChooseAction from './screens/ChooseAction'
import Onboarding from './screens/Onboarding'
import ShoppingList from './screens/ShoppingList'
import SilpoConnect from './screens/SilpoConnect'

function Loading({ text = 'Вмикаємось…' }) {
  return <div className="center"><div className="spinner" />{text}</div>
}

/**
 * Єдиний потік агента з макетів:
 * онбординг → запуск → живий трейс → кошик → вибір дії → результат.
 */
export default function App() {
  const [state, setState] = useState({ status: 'boot' })
  const [screen, setScreen] = useState('start')
  const [goals, setGoals] = useState(null)
  const [context, setContext] = useState(null)
  const [run, setRun] = useState({ steps: [], draft: [], summary: {}, building: false })
  const [applying, setApplying] = useState(false)
  const [applyResult, setApplyResult] = useState(null)
  const [list, setList] = useState(null)
  const [saving, setSaving] = useState(false)
  const poll = useRef(null)

  useEffect(() => { initTelegram() }, [])

  const boot = useCallback(async () => {
    try {
      const session = await login()
      if (!session.silpo_connected) {
        setState({ status: 'connect', user: session.user })
        return
      }
      const goalState = await api.getGoals().catch(() => null)
      setGoals(goalState)
      setState({ status: 'ready', user: session.user })
      setScreen(goalState?.configured ? 'start' : 'onboarding')
      api.agentContext().then(setContext).catch(() => {})
    } catch (e) {
      setState({ status: 'error', message: e.message })
    }
  }, [])

  useEffect(() => { boot() }, [boot])

  useEffect(() => () => clearInterval(poll.current), [])

  async function saveGoals(payload) {
    setSaving(true)
    try {
      await api.saveGoals(payload)
      setGoals(await api.getGoals())
      setScreen('start')
      api.agentContext().then(setContext).catch(() => {})
    } catch (e) {
      WebApp.showAlert?.(`Не вдалось зберегти: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  /** Запускає агента й опитує статус, поки той працює — трейс іде наживо. */
  async function startAgent() {
    setRun({ steps: [], draft: [], summary: {}, building: true, error: null })
    setApplyResult(null)
    setScreen('running')
    try {
      await api.agentStart()
    } catch (e) {
      setRun((r) => ({ ...r, building: false, error: e.message }))
      return
    }
    clearInterval(poll.current)
    poll.current = setInterval(async () => {
      try {
        const data = await api.agentStatus()
        setRun(data)
        if (!data.building) {
          clearInterval(poll.current)
          if (!data.error) notify('success')
        }
      } catch { /* мережа моргнула — наступна спроба за 2 секунди */ }
    }, 2000)
  }

  async function applyToCart() {
    setApplying(true)
    try {
      setApplyResult(await api.agentApply())
      notify('success')
    } catch (e) {
      notify('error')
      WebApp.showAlert?.(`Не вдалось додати: ${e.message}`)
    } finally {
      setApplying(false)
    }
  }

  async function openList() {
    try {
      setList(await api.shoppingList())
      setScreen('list')
    } catch (e) {
      WebApp.showAlert?.(e.message)
    }
  }

  if (state.status === 'boot') return <Loading />
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

  if (screen === 'onboarding') return <Onboarding onDone={saveGoals} saving={saving} />

  if (screen === 'running') {
    return (
      <AgentRun
        steps={run.steps || []}
        building={run.building}
        error={run.error}
        onBack={() => setScreen('start')}
        onOpenBasket={() => setScreen('basket')}
      />
    )
  }

  if (screen === 'basket') {
    return (
      <Basket
        draft={run.draft || []}
        summary={run.summary || {}}
        answer={run.answer}
        onBack={() => setScreen('running')}
        onNext={() => setScreen('action')}
      />
    )
  }

  if (screen === 'action') {
    return (
      <ChooseAction
        applying={applying}
        result={applyResult}
        onApply={applyToCart}
        onList={openList}
        onBack={() => setScreen('basket')}
      />
    )
  }

  if (screen === 'list') return <ShoppingList list={list} onBack={() => setScreen('action')} />

  return (
    <AgentStart
      context={context}
      goalLabel={goals?.targets?.goal_label || context?.profile?.goal_label}
      running={run.building}
      onRun={startAgent}
    />
  )
}
