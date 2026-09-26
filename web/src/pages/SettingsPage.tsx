import { useCapabilities, useConfig } from '../engine/hooks'
import { DEFAULT_CONFIG, type ExecutionPreference } from '../lib/config'

export function SettingsPage() {
  const [config, update] = useConfig()
  const caps = useCapabilities()
  return (
    <>
      <div className="page-header">
        <h1>Settings</h1>
      </div>
      <div className="grid-2">
        <div className="panel stack">
          <h3>Where work runs</h3>
          <label className="field">
            Execution
            <select value={config.execution} onChange={(e) => update({ execution: e.target.value as ExecutionPreference })}>
              <option value="auto">On this computer, fastest available (recommended)</option>
              <option value="webgpu" disabled={!caps?.webgpu}>
                On this computer, using the graphics card
              </option>
              <option value="wasm">On this computer, using the main processor only</option>
            </select>
          </label>
          <label className="field">
            Parallel jobs
            <input type="number" min={1} max={8} value={config.batchSize} onChange={(e) => update({ batchSize: Math.max(1, Math.min(8, Number(e.target.value) || 1)) })} style={{ width: 70 }} />
          </label>
        </div>
        <div className="panel stack">
          <h3>This device</h3>
          {caps ? (
            <ul className="muted">
              <li>WebGPU: {caps.webgpu ? 'yes' : 'no'}</li>
              <li>WebCodecs: {caps.webcodecs ? 'yes' : 'no'}</li>
              <li>Cross-origin isolated (multi-threaded WASM): {caps.crossOriginIsolated ? 'yes' : 'no'}</li>
              <li>CPU threads: {caps.hardwareConcurrency}</li>
              <li>Memory: {caps.deviceMemoryGb ? `${caps.deviceMemoryGb} GB (approx.)` : 'unknown'}</li>
            </ul>
          ) : (
            <p className="muted">Probing…</p>
          )}
          <h3>Face Smudge defaults</h3>
          <div className="row">
            <label className="field">
              Radius (px)
              <input type="number" min={1} max={500} value={config.smudge.blurRadius} onChange={(e) => update((c) => ({ ...c, smudge: { ...c.smudge, blurRadius: Number(e.target.value) || 50 } }))} style={{ width: 80 }} />
            </label>
            <label className="field">
              Sigma
              <input type="number" min={1} max={200} value={config.smudge.blurSigma} onChange={(e) => update((c) => ({ ...c, smudge: { ...c.smudge, blurSigma: Number(e.target.value) || 25 } }))} style={{ width: 80 }} />
            </label>
            <label className="field">
              Frame cache
              <input type="number" min={10} max={500} value={config.smudge.cacheSize} onChange={(e) => update((c) => ({ ...c, smudge: { ...c.smudge, cacheSize: Number(e.target.value) || 100 } }))} style={{ width: 80 }} />
            </label>
          </div>
          <div>
            <button className="secondary" onClick={() => update(() => structuredClone(DEFAULT_CONFIG))}>
              Reset all settings
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
