import { DropZone } from '../components/DropZone'
import { JobTable } from '../components/JobTable'
import { engine } from '../engine'
import { useCapabilities, useConfig, useJobs } from '../engine/hooks'
import type { FaceBlurOptions } from '../faceblur/options'
import { isImageFile, isVideoFile } from '../lib/files'

const ACCEPT = '.jpg,.jpeg,.png,.bmp,.webp,.mp4,.mov,.m4v,image/*,video/mp4,video/quicktime'

export function FaceBlurPage() {
  const jobs = useJobs().filter((j) => j.request.kind === 'face-blur')
  const [config, update] = useConfig()
  const caps = useCapabilities()
  const opts = config.faceBlur
  const set = (patch: Partial<FaceBlurOptions>) => update((c) => ({ ...c, faceBlur: { ...c.faceBlur, ...patch } }))

  const addFiles = (files: File[]) => {
    for (const file of files) {
      if (!isImageFile(file) && !isVideoFile(file)) continue
      engine.queue.add({ kind: 'face-blur', file, options: { ...opts } })
    }
  }
  const pending = jobs.filter((j) => j.status === 'pending').length
  const running = jobs.filter((j) => j.status === 'processing').length

  return (
    <>
      <div className="page-header">
        <h1>Blur Faces</h1>
        <span className="muted small">Runs the same CenterFace detector as the desktop app.</span>
      </div>
      {caps && !caps.webcodecs && <div className="notice">This browser lacks WebCodecs, so only images can be processed here. Videos need Chrome, Edge, Safari 16.4+ or Firefox 130+.</div>}
      <div className="grid-2">
        <div className="panel stack">
          <h3>Files</h3>
          <DropZone accept={ACCEPT} label="Drop images or videos here" hint="JPG, PNG, WebP, MP4, MOV. Nothing leaves this device." onFiles={addFiles} />
          <div className="row">
            <button onClick={() => engine.queue.start()} disabled={pending === 0}>
              Start ({pending})
            </button>
            <button className="secondary" onClick={() => engine.queue.cancelAll()} disabled={running + pending === 0}>
              Cancel all
            </button>
            <button className="secondary" onClick={() => engine.queue.clearFinished()}>
              Clear finished
            </button>
            <label className="field inline">
              Parallel jobs
              <input type="number" min={1} max={8} value={config.batchSize} onChange={(e) => update({ batchSize: Math.max(1, Math.min(8, Number(e.target.value) || 1)) })} style={{ width: 60 }} />
            </label>
          </div>
        </div>
        <div className="panel stack">
          <h3>Options</h3>
          <label className="field">
            Detection threshold: {opts.thresh.toFixed(2)} <span className="small">lower finds more faces, higher avoids false positives</span>
            <input type="range" min={0.01} max={0.99} step={0.01} value={opts.thresh} onChange={(e) => set({ thresh: Number(e.target.value) })} />
          </label>
          <label className="field">
            Mask scale: {opts.maskScale.toFixed(2)}
            <input type="range" min={1} max={2} step={0.05} value={opts.maskScale} onChange={(e) => set({ maskScale: Number(e.target.value) })} />
          </label>
          <div className="row">
            <label className="field">
              Replace with
              <select value={opts.replacewith} onChange={(e) => set({ replacewith: e.target.value as FaceBlurOptions['replacewith'] })}>
                <option value="blur">Blur</option>
                <option value="solid">Solid black</option>
                <option value="mosaic">Mosaic</option>
                <option value="none">None (detect only)</option>
              </select>
            </label>
            <label className="field">
              Detector input
              <select value={['auto', 'full'].includes(opts.scale) ? opts.scale : 'custom'} onChange={(e) => set({ scale: e.target.value === 'custom' ? '640x360' : e.target.value })}>
                <option value="auto">Auto (longest side 640)</option>
                <option value="full">Full resolution (slow)</option>
                <option value="custom">Custom size</option>
              </select>
            </label>
            {!['auto', 'full'].includes(opts.scale) && (
              <label className="field">
                Width x Height
                <input type="text" value={opts.scale} onChange={(e) => set({ scale: e.target.value })} style={{ width: 110 }} />
              </label>
            )}
            {opts.replacewith === 'mosaic' && (
              <label className="field">
                Mosaic size
                <input type="number" min={2} max={100} value={opts.mosaicSize} onChange={(e) => set({ mosaicSize: Number(e.target.value) || 20 })} style={{ width: 70 }} />
              </label>
            )}
          </div>
          <label className="field inline">
            <input type="checkbox" checked={opts.boxes} onChange={(e) => set({ boxes: e.target.checked })} /> Rectangular masks instead of ellipses
          </label>
          <label className="field inline">
            <input type="checkbox" checked={opts.keepAudio} onChange={(e) => set({ keepAudio: e.target.checked })} /> Keep audio track
          </label>
          <label className="field inline">
            <input type="checkbox" checked={opts.keepMetadata} onChange={(e) => set({ keepMetadata: e.target.checked })} /> Keep image metadata (EXIF)
          </label>
        </div>
      </div>
      <div className="panel">
        <h3>Queue</h3>
        <JobTable jobs={jobs} />
      </div>
    </>
  )
}
