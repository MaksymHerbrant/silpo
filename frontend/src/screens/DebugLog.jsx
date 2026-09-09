/**
 * Демо-панель для журі: сирі JSON-RPC виклики до https://mcp.silpo.ua/mcp
 * за поточну сесію — видимий доказ реальних tools/call.
 */
export default function DebugLog({ log, tools, onRefresh, onLoadTools }) {
  const entries = log?.entries || []

  return (
    <div className="screen">
      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>MCP-лог</h2>
          <span className="tag">{log?.demo_mode ? 'DEMO' : 'LIVE'}</span>
        </div>
        <p className="muted" style={{ marginTop: 6 }}>{log?.endpoint}</p>
        <div className="row" style={{ marginTop: 12, gap: 10 }}>
          <button className="btn secondary" onClick={onRefresh}>Оновити лог</button>
          <button className="btn secondary" onClick={onLoadTools}>tools/list</button>
        </div>
      </div>

      {tools && (
        <div className="card">
          <h3>Доступні tools ({tools.count})</h3>
          <p className="muted">{tools.tools.map((t) => t.name).join(', ')}</p>
        </div>
      )}

      <div className="card">
        <h3>Останні виклики ({entries.length})</h3>
        {entries.length === 0 && <p className="muted">Викликів ще не було.</p>}
        {entries.map((e) => (
          <div className="log-entry" key={e.seq}>
            <div className="row">
              <strong>#{e.seq} {e.tool}</strong>
              <span className={`tag${e.status === 'error' ? ' err' : ''}`}>
                {e.status} · {e.duration_ms} ms
              </span>
            </div>
            <pre>{JSON.stringify(e.jsonrpc_request, null, 1)}</pre>
            <pre style={{ opacity: 0.75 }}>
              {JSON.stringify(e.jsonrpc_response, null, 1)?.slice(0, 700)}
            </pre>
          </div>
        ))}
      </div>
    </div>
  )
}
