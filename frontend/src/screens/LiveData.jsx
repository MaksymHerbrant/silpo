import { useEffect, useState } from 'react'
import Screen from '../components/Screen'
import { api } from '../lib/api'

/**
 * «Живі дані» — доказ, що все відбулось через MCP Сільпо, а не намальовано.
 *
 * Для гостя це перелік зрозумілих дій. Для журі є перемикач у технічний
 * режим із сирими JSON-RPC викликами.
 */
export default function LiveData({ onBack }) {
  const [data, setData] = useState(null)
  const [raw, setRaw] = useState(null)
  const [tech, setTech] = useState(false)

  useEffect(() => {
    api.liveActivity().then(setData).catch(() => setData({ steps: [] }))
  }, [])

  useEffect(() => {
    if (tech && !raw) api.mcpLog(60).then(setRaw).catch(() => setRaw({ entries: [] }))
  }, [tech, raw])

  return (
    <Screen title="Живі дані" onBack={onBack}>
      <div>
        <h1>Усе через MCP Сільпо</h1>
        <p className="lede">
          Застосунок не має власної бази товарів. Кожна цифра нижче прийшла
          з офіційного API «Сільпо» просто зараз.
        </p>
      </div>

      {data && (
        <div className="stat-grid">
          <div className="stat-tile">
            <div className="n">{data.total_calls ?? 0}</div>
            <div className="t">викликів за сесію</div>
          </div>
          <div className="stat-tile">
            <div className="n">{data.tools_used ?? 0}</div>
            <div className="t">різних інструментів</div>
          </div>
        </div>
      )}

      <div className="card plain">
        {(data?.steps || []).map((s) => (
          <div className="live-row" key={s.tool}>
            <span className={`live-dot${s.done ? ' on' : ''}`}>{s.done ? '✓' : '·'}</span>
            <span className="live-body">
              <span className="live-label">
                {s.label}
                {s.is_write && <span className="tag warn" style={{ marginLeft: 8 }}>запис</span>}
              </span>
              <span className="live-tool">{s.tool}</span>
            </span>
            <span className="live-calls">{s.calls || '—'}</span>
          </div>
        ))}
      </div>

      <button className="disclose" onClick={() => setTech((v) => !v)}>
        <span>Технічний режим — сирі JSON-RPC виклики</span>
        <span className="chev">{tech ? '−' : '+'}</span>
      </button>

      {tech && (
        <div className="card plain">
          <p className="over-note" style={{ marginTop: 0 }}>
            Ендпоінт: <code>{data?.endpoint}</code>
          </p>
          {(raw?.entries || []).slice(0, 25).map((e, i) => (
            <div className="hist-row" key={i}>
              <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
                {e.tool || e.name}
              </span>
              <span className="d">{e.duration_ms ? `${Math.round(e.duration_ms)} мс` : ''}</span>
            </div>
          ))}
          {!raw?.entries?.length && <p className="muted">Лог порожній.</p>}
        </div>
      )}
    </Screen>
  )
}
