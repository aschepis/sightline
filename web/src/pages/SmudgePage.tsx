import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react'
import { DropZone } from '../components/DropZone'
import { JobTable } from '../components/JobTable'
import { engine } from '../engine'
import { useCapabilities, useConfig, useJobs } from '../engine/hooks'
import { downloadBlob, formatDuration, isVideoFile, outputFilename } from '../lib/files'
import { FrameSource } from '../smudge/FrameSource'
import { applyOperations, createOperation, parseOperations, serializeOperations, type SmudgeOperation } from '../smudge/ops'

const SPEEDS = [0.25, 0.5, 1, 1.5, 2]

export function SmudgePage() {
  const caps = useCapabilities()
  const [config, update] = useConfig()
  const jobs = useJobs().filter((j) => j.request.kind === 'smudge-export')
  const [file, setFile] = useState<File | null>(null)
  const [source, setSource] = useState<FrameSource | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(config.smudge.playbackSpeed)
  const [ops, setOps] = useState<SmudgeOperation[]>([])
  const [redo, setRedo] = useState<SmudgeOperation[][]>([])
  const [strokes, setStrokes] = useState<SmudgeOperation[][]>([])
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const drawing = useRef<SmudgeOperation[] | null>(null)
  const radius = config.smudge.blurRadius
  const sigma = config.smudge.blurSigma

  const open = async (files: File[]) => {
    const f = files[0]
    if (!f || !isVideoFile(f)) return
    source?.close()
    setSource(null)
    setError(null)
    setOps([])
    setStrokes([])
    setRedo([])
    setFrame(0)
    setPlaying(false)
    setFile(f)
    try {
      const s = await FrameSource.open(f, config.smudge.cacheSize)
      setSource(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => () => source?.close(), [source])

  const render = useCallback(async () => {
    const canvas = canvasRef.current
    if (!canvas || !source) return
    let bitmap: ImageBitmap
    try {
      bitmap = await source.getFrame(frame)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return
    }
    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
      canvas.width = bitmap.width
      canvas.height = bitmap.height
    }
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!
    ctx.drawImage(bitmap, 0, 0)
    const frameOps = ops.filter((o) => o.frame === frame)
    if (frameOps.length > 0) {
      const image = ctx.getImageData(0, 0, canvas.width, canvas.height)
      applyOperations(image, frameOps)
      ctx.putImageData(image, 0, 0)
    }
    if (cursor && !playing) {
      ctx.beginPath()
      ctx.arc(cursor.x * canvas.width, cursor.y * canvas.height, radius, 0, Math.PI * 2)
      ctx.strokeStyle = '#00a6ff'
      ctx.lineWidth = 2
      ctx.stroke()
    }
  }, [source, frame, ops, cursor, playing, radius])

  useEffect(() => {
    void render()
  }, [render])

  useEffect(() => {
    if (!playing || !source) return
    const interval = 1000 / (source.fps * speed)
    const timer = setInterval(() => {
      setFrame((f) => {
        if (f + 1 >= source.frameCount) {
          setPlaying(false)
          return f
        }
        return f + 1
      })
    }, interval)
    return () => clearInterval(timer)
  }, [playing, speed, source])

  const undoStroke = () => {
    setStrokes((s) => {
      const last = s[s.length - 1]
      if (!last) return s
      const ids = new Set(last.map((o) => o.id))
      setOps((o) => o.filter((op) => !ids.has(op.id)))
      setRedo((r) => [...r, last])
      return s.slice(0, -1)
    })
  }
  const redoStroke = () => {
    setRedo((r) => {
      const last = r[r.length - 1]
      if (!last) return r
      setOps((o) => [...o, ...last])
      setStrokes((s) => [...s, last])
      return r.slice(0, -1)
    })
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return
      if (!source) return
      if (e.key === ' ') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (e.key === 'ArrowRight') setFrame((f) => Math.min(source.frameCount - 1, f + 1))
      else if (e.key === 'ArrowLeft') setFrame((f) => Math.max(0, f - 1))
      else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) redoStroke()
        else undoStroke()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const toFrameCoords = (e: PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    return { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }
  }

  const onPointerDown = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!source) return
    setPlaying(false)
    const { x, y } = toFrameCoords(e)
    const op = createOperation(frame, x, y, radius, sigma)
    drawing.current = [op]
    setOps((o) => [...o, op])
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = toFrameCoords(e)
    setCursor({ x, y })
    const stroke = drawing.current
    if (!stroke || !canvasRef.current) return
    const last = stroke[stroke.length - 1]
    const dx = (x - last.x) * canvasRef.current.width
    const dy = (y - last.y) * canvasRef.current.height
    // Add a point once the pointer has moved a third of the radius, like a brush.
    if (Math.hypot(dx, dy) < radius / 3) return
    const op = createOperation(frame, x, y, radius, sigma)
    stroke.push(op)
    setOps((o) => [...o, op])
  }
  const onPointerUp = () => {
    const stroke = drawing.current
    drawing.current = null
    if (stroke) {
      setStrokes((s) => [...s, stroke])
      setRedo([])
    }
  }

  const clearAll = () => {
    setOps([])
    setStrokes([])
    setRedo([])
  }

  const exportVideo = () => {
    if (!file) return
    engine.queue.add({ kind: 'smudge-export', file, operations: ops })
    engine.queue.start()
  }

  const loadOps = async (files: File[]) => {
    const f = files[0]
    if (!f) return
    try {
      const loaded = parseOperations(await f.text())
      setOps(loaded)
      setStrokes(loaded.map((o) => [o]))
      setRedo([])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Face Smudge</h1>
        <span className="muted small">Click or drag on the frame to blur. Space plays, arrows step, ⌘Z undoes.</span>
      </div>
      {caps && !caps.webcodecs && <div className="notice">This browser lacks WebCodecs, which the editor needs for frame-accurate seeking.</div>}
      {error && <div className="notice">{error}</div>}
      {!source && (
        <div className="panel">
          <DropZone accept=".mp4,.mov,.m4v,video/mp4,video/quicktime" multiple={false} label={file ? `Opening ${file.name}…` : 'Drop a video to edit'} hint="MP4 or MOV" onFiles={open} />
        </div>
      )}
      {source && (
        <div className="grid-2" style={{ gridTemplateColumns: '2fr 1fr' }}>
          <div className="panel stack">
            <canvas
              ref={canvasRef}
              className="editor-canvas"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={() => {
                onPointerUp()
                setCursor(null)
              }}
            />
            <div className="transport">
              <button className="secondary icon" onClick={() => setFrame(0)} title="Jump to start">
                ⏮
              </button>
              <button className="secondary icon" onClick={() => setFrame((f) => Math.max(0, f - 1))} title="Step back">
                ◀
              </button>
              <button className="icon" onClick={() => setPlaying((p) => !p)}>
                {playing ? 'Pause' : 'Play'}
              </button>
              <button className="secondary icon" onClick={() => setFrame((f) => Math.min(source.frameCount - 1, f + 1))} title="Step forward">
                ▶
              </button>
              <button className="secondary icon" onClick={() => setFrame(source.frameCount - 1)} title="Jump to end">
                ⏭
              </button>
              <input className="scrubber" type="range" min={0} max={source.frameCount - 1} value={frame} onChange={(e) => setFrame(Number(e.target.value))} />
              <span className="small muted" style={{ minWidth: 150 }}>
                Frame {frame + 1} / {source.frameCount} · {formatDuration(source.timeOf(frame))}
              </span>
              <select
                value={speed}
                onChange={(e) => {
                  const s = Number(e.target.value)
                  setSpeed(s)
                  update((c) => ({ ...c, smudge: { ...c.smudge, playbackSpeed: s } }))
                }}
              >
                {SPEEDS.map((s) => (
                  <option key={s} value={s}>
                    {s}x
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="panel stack">
            <h3>Brush</h3>
            <label className="field">
              Radius: {radius}px
              <input type="range" min={5} max={300} value={radius} onChange={(e) => update((c) => ({ ...c, smudge: { ...c.smudge, blurRadius: Number(e.target.value) } }))} />
            </label>
            <label className="field">
              Blur strength (sigma): {sigma}
              <input type="range" min={1} max={100} value={sigma} onChange={(e) => update((c) => ({ ...c, smudge: { ...c.smudge, blurSigma: Number(e.target.value) } }))} />
            </label>
            <h3>Edits</h3>
            <div className="row">
              <button className="secondary" onClick={undoStroke} disabled={strokes.length === 0}>
                Undo
              </button>
              <button className="secondary" onClick={redoStroke} disabled={redo.length === 0}>
                Redo
              </button>
              <button className="secondary" onClick={clearAll} disabled={ops.length === 0}>
                Clear all
              </button>
            </div>
            <p className="small muted">
              {ops.length} smudge(s) on {new Set(ops.map((o) => o.frame)).size} frame(s)
            </p>
            <div className="row">
              <button className="secondary" onClick={() => file && downloadBlob(new Blob([serializeOperations(ops, file.name)], { type: 'application/json' }), outputFilename(file.name, '_smudges', '.json'))} disabled={ops.length === 0}>
                Save edits
              </button>
              <label className="button secondary">
                Load edits
                <input type="file" accept=".json" hidden onChange={(e) => e.target.files && loadOps(Array.from(e.target.files))} />
              </label>
            </div>
            <h3>Export</h3>
            <button onClick={exportVideo} disabled={ops.length === 0}>
              Export video
            </button>
            <button
              className="secondary"
              onClick={() => {
                source.close()
                setSource(null)
                setFile(null)
              }}
            >
              Close video
            </button>
          </div>
        </div>
      )}
      {jobs.length > 0 && (
        <div className="panel">
          <h3>Exports</h3>
          <JobTable jobs={jobs} />
        </div>
      )}
    </>
  )
}
