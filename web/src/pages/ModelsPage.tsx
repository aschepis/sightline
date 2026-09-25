import { useEffect, useState } from 'react'
import { clearAllModels, deleteCachedModel, formatBytes, listCachedModels, type CachedModelEntry } from '../lib/modelCache'
import { EMBEDDING_MODEL, SEGMENTATION_MODEL, WHISPER_MODELS } from '../transcribe/types'

export function ModelsPage() {
  const [entries, setEntries] = useState<CachedModelEntry[]>([])
  const [busy, setBusy] = useState(false)
  const refresh = () => listCachedModels().then(setEntries)
  useEffect(() => {
    void refresh()
  }, [])
  const total = entries.reduce((n, e) => n + e.bytes, 0)
  const groups = groupByModel(entries)

  return (
    <>
      <div className="page-header">
        <h1>Models</h1>
        <span className="muted small">The recognition software each tool uses. Downloaded once, kept in this browser, and it works without internet afterwards.</span>
      </div>
      <div className="panel stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span>
            {entries.length} file(s) stored in this browser, {formatBytes(total)}. These are the only downloads Sightline makes; your own files are never uploaded.
          </span>
          <div className="row">
            <button className="secondary" onClick={() => void refresh()}>
              Refresh
            </button>
            <button
              className="danger"
              disabled={busy || entries.length === 0}
              onClick={async () => {
                setBusy(true)
                await clearAllModels()
                await refresh()
                setBusy(false)
              }}
            >
              Delete all
            </button>
          </div>
        </div>
        {groups.length === 0 && <p className="muted">Nothing cached yet. Models download the first time you run a tool.</p>}
        {groups.map((g) => (
          <div className="row" key={g.name} style={{ justifyContent: 'space-between', borderBottom: '1px solid var(--border)', padding: '6px 0' }}>
            <div>
              <div>{g.name}</div>
              <div className="small muted">
                {g.files.length} file(s) · {formatBytes(g.bytes)}
              </div>
            </div>
            <button
              className="secondary icon"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                for (const f of g.files) await deleteCachedModel(f)
                await refresh()
                setBusy(false)
              }}
            >
              Delete
            </button>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3>What each tool needs</h3>
        <ul className="muted">
          <li>Blur Faces: CenterFace, 7 MB, bundled with the app.</li>
          <li>Face Smudge: no model.</li>
          <li>
            Transcription: one Whisper model ({WHISPER_MODELS.map((m) => m.approxSize).join(', ')}), plus {SEGMENTATION_MODEL} (~6 MB) and {EMBEDDING_MODEL} (~90 MB) for speaker labels.
          </li>
        </ul>
      </div>
    </>
  )
}

function groupByModel(entries: CachedModelEntry[]): Array<{ name: string; bytes: number; files: CachedModelEntry[] }> {
  const map = new Map<string, { name: string; bytes: number; files: CachedModelEntry[] }>()
  for (const e of entries) {
    const m = /huggingface\.co\/([^/]+\/[^/]+)/.exec(e.url)
    const name = m ? m[1] : e.url.includes('centerface') ? 'CenterFace (face detector)' : new URL(e.url).pathname
    const g = map.get(name) ?? { name, bytes: 0, files: [] }
    g.bytes += e.bytes
    g.files.push(e)
    map.set(name, g)
  }
  return [...map.values()].sort((a, b) => b.bytes - a.bytes)
}
