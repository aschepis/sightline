import { useEffect, useRef, useState } from 'react'
import { engine } from '../engine'
import { useCapabilities } from '../engine/hooks'
import { preloadFaceDetector } from '../faceblur/detector'
import { clearAllModels, deleteCachedModel, formatBytes, listCachedModels, type CachedModelEntry } from '../lib/modelCache'
import type { TranscribeWorkerEvent, TranscribeWorkerRequest } from '../transcribe/worker'
import { EMBEDDING_MODEL, SEGMENTATION_MODEL, WHISPER_MODELS } from '../transcribe/types'

interface ModelRow {
  key: string
  label: string
  usedBy: string
  approxSize: string
  /** Which cached URLs belong to this row. */
  matches: (url: string) => boolean
  /** What to send to the transcription worker, or 'centerface' for the detector. */
  download: 'centerface' | 'speakers' | string
}

const ROWS: ModelRow[] = [
  { key: 'centerface', label: 'Face detector (CenterFace)', usedBy: 'Blur Faces', approxSize: '7 MB', matches: (u) => u.includes('centerface'), download: 'centerface' },
  ...WHISPER_MODELS.map((m) => ({
    key: m.id,
    label: m.label.replace(' (desktop default)', ''),
    usedBy: 'Transcription',
    approxSize: m.approxSize,
    matches: (u: string) => u.includes(`huggingface.co/${m.id}/`),
    download: m.id,
  })),
  {
    key: 'speakers',
    label: 'Speaker identification (pyannote + WavLM)',
    usedBy: 'Transcription, "Identify speakers"',
    approxSize: '~390 MB',
    matches: (u) => u.includes(`huggingface.co/${SEGMENTATION_MODEL}/`) || u.includes(`huggingface.co/${EMBEDDING_MODEL}/`),
    download: 'speakers',
  },
]

type Progress = { fraction: number; message: string; error?: string }

export function ModelsPage() {
  const caps = useCapabilities()
  const [entries, setEntries] = useState<CachedModelEntry[]>([])
  const [progress, setProgress] = useState<Record<string, Progress>>({})
  const [busy, setBusy] = useState(false)
  const worker = useRef<Worker | null>(null)
  const refresh = () => listCachedModels().then(setEntries)
  useEffect(() => {
    void refresh()
    return () => worker.current?.terminate()
  }, [])
  const total = entries.reduce((n, e) => n + e.bytes, 0)

  const isReady = (row: ModelRow) => entries.some((e) => row.matches(e.url) && e.url.endsWith('.onnx'))
  const sizeOf = (row: ModelRow) => entries.filter((e) => row.matches(e.url)).reduce((n, e) => n + e.bytes, 0)
  const setRowProgress = (key: string, p: Progress | null) =>
    setProgress((prev) => {
      const next = { ...prev }
      if (p) next[key] = p
      else delete next[key]
      return next
    })

  const download = async (row: ModelRow) => {
    setRowProgress(row.key, { fraction: 0, message: 'Starting' })
    try {
      if (row.download === 'centerface') {
        await preloadFaceDetector((loaded, t) => setRowProgress(row.key, { fraction: t ? loaded / t : 0, message: `${formatBytes(loaded)} of ${formatBytes(t)}` }))
      } else {
        await preloadInWorker(row.download, (fraction, message) => setRowProgress(row.key, { fraction, message }))
      }
      setRowProgress(row.key, null)
    } catch (err) {
      setRowProgress(row.key, { fraction: 0, message: '', error: err instanceof Error ? err.message : String(err) })
    }
    await refresh()
  }

  const preloadInWorker = (model: string, onProgress: (fraction: number, message: string) => void) =>
    new Promise<void>((resolve, reject) => {
      const w = worker.current ?? new Worker(new URL('../transcribe/worker.ts', import.meta.url), { type: 'module' })
      worker.current = w
      const id = crypto.randomUUID()
      const onMessage = (event: MessageEvent<TranscribeWorkerEvent>) => {
        const msg = event.data
        if (msg.id !== id) return
        if (msg.type === 'progress') onProgress(msg.fraction, msg.message ?? '')
        else if (msg.type === 'preloaded') {
          w.removeEventListener('message', onMessage)
          resolve()
        } else if (msg.type === 'error') {
          w.removeEventListener('message', onMessage)
          reject(new Error(msg.message))
        }
      }
      w.addEventListener('message', onMessage)
      const backend = engine.activeBackend() === 'webgpu' ? 'webgpu' : 'wasm'
      const request: TranscribeWorkerRequest = { type: 'preload', id, model, backend }
      w.postMessage(request)
    })

  const downloadAll = async () => {
    setBusy(true)
    for (const row of ROWS) {
      if (!isReady(row)) await download(row)
    }
    setBusy(false)
  }

  const missing = ROWS.filter((r) => !isReady(r))

  return (
    <>
      <div className="page-header">
        <h1>Models</h1>
        <span className="muted small">The recognition software each tool uses. Downloaded once, kept in this browser, and it works without internet afterwards.</span>
      </div>
      <div className="notice info" style={{ marginBottom: 16 }}>
        These downloads are the only time Sightline uses the internet. Your own photos, videos and recordings are never uploaded. Download what you need now and the tools will
        work later even with no connection.
        {caps && !caps.webgpu && ' Files are fetched in the form this computer uses (main processor), so switching devices may need a fresh download.'}
      </div>
      <div className="panel stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span>
            {formatBytes(total)} stored in this browser across {entries.length} file(s)
          </span>
          <div className="row">
            <button onClick={downloadAll} disabled={busy || missing.length === 0 || Object.keys(progress).length > 0}>
              Download everything for offline use
            </button>
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
        <table className="jobs">
          <thead>
            <tr>
              <th>Model</th>
              <th>Used by</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => {
              const ready = isReady(row)
              const p = progress[row.key]
              return (
                <tr key={row.key}>
                  <td>
                    <div>{row.label}</div>
                    <div className="small muted">about {row.approxSize}</div>
                  </td>
                  <td className="muted">{row.usedBy}</td>
                  <td>
                    {p && !p.error ? (
                      <div className="stack" style={{ gap: 4 }}>
                        <div className="progress">
                          <div style={{ width: `${Math.round(p.fraction * 100)}%` }} />
                        </div>
                        <span className="small muted">{p.message}</span>
                      </div>
                    ) : p?.error ? (
                      <span className="badge failed" title={p.error}>
                        Failed
                      </span>
                    ) : ready ? (
                      <span className="badge success">Ready · {formatBytes(sizeOf(row))}</span>
                    ) : (
                      <span className="badge pending">Not downloaded</span>
                    )}
                  </td>
                  <td className="row" style={{ justifyContent: 'flex-end' }}>
                    {!ready && (
                      <button className="icon" disabled={!!p && !p.error} onClick={() => download(row)}>
                        Download
                      </button>
                    )}
                    {ready && (
                      <button
                        className="icon secondary"
                        disabled={busy}
                        onClick={async () => {
                          setBusy(true)
                          for (const e of entries.filter((e) => row.matches(e.url))) await deleteCachedModel(e)
                          await refresh()
                          setBusy(false)
                        }}
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Whisper "base" plus speaker identification is enough for most transcription work, about 670 MB together on a computer with graphics-card support and less on one
        without. The large-v3 turbo model is the most accurate but needs a graphics card and a much longer first download.
      </p>
    </>
  )
}
