import { useRef, useState } from 'react'
import { DropZone } from '../components/DropZone'
import { JobTable } from '../components/JobTable'
import { engine } from '../engine'
import { useCapabilities, useConfig, useJobs } from '../engine/hooks'
import type { Job } from '../engine/types'
import { downloadBlob, isAudioFile, isVideoFile, outputFilename } from '../lib/files'
import { displayName, renameSpeakers, speakerLabels, toJson, toSrt, toText, type SpeakerNames } from '../transcribe/format'
import { WHISPER_MODELS, type TranscriptResult } from '../transcribe/types'

const LANGUAGES = [
  ['auto', 'Detect automatically'],
  ['en', 'English'],
  ['es', 'Spanish'],
  ['fr', 'French'],
  ['de', 'German'],
  ['pt', 'Portuguese'],
  ['it', 'Italian'],
  ['zh', 'Chinese'],
  ['ja', 'Japanese'],
  ['ar', 'Arabic'],
  ['ru', 'Russian'],
]

export function TranscribePage() {
  const jobs = useJobs().filter((j) => j.request.kind === 'transcribe')
  const [config, update] = useConfig()
  const caps = useCapabilities()
  const [viewing, setViewing] = useState<Job | null>(null)
  const t = config.transcription
  const set = (patch: Partial<typeof t>) => update((c) => ({ ...c, transcription: { ...c.transcription, ...patch } }))

  const addFiles = (files: File[]) => {
    for (const file of files) {
      if (!isAudioFile(file) && !isVideoFile(file)) continue
      engine.queue.add({ kind: 'transcribe', file, options: { model: t.model, language: t.language, diarize: t.diarize, numSpeakers: t.numSpeakers } })
    }
  }
  const pending = jobs.filter((j) => j.status === 'pending').length
  const result = viewing?.output?.kind === 'transcribe' ? viewing.output.result : null
  const [names, setNames] = useState<SpeakerNames>({})
  const nameInputs = useRef<Record<string, HTMLInputElement | null>>({})

  // Names are remembered per file so a re-run does not mean retyping them.
  const openTranscript = (job: Job) => {
    setNames(loadSpeakerNames(job.request.file.name))
    setViewing(job)
  }
  const setName = (label: string, value: string) => {
    if (!viewing) return
    const next = { ...names, [label]: value }
    setNames(next)
    saveSpeakerNames(viewing.request.file.name, next)
  }

  const save = (format: 'txt' | 'srt' | 'json') => {
    if (!viewing || !result) return
    const name = viewing.request.file.name
    const named = renameSpeakers(result, names)
    const content = format === 'txt' ? toText(named, name) : format === 'srt' ? toSrt(named) : toJson(result, names)
    downloadBlob(new Blob([content], { type: 'text/plain' }), outputFilename(name, '_transcript', `.${format}`))
  }

  return (
    <>
      <div className="page-header">
        <h1>Transcription</h1>
        <span className="muted small">Your recordings are transcribed on your computer, not sent to a service.</span>
      </div>
      {caps && !caps.webgpu && <div className="notice info">This browser cannot use your graphics card for speed, so transcription runs on the main processor. Expect it to take about as long as the recording itself with the "base" model, and longer with bigger models.</div>}
      <div className="grid-2">
        <div className="panel stack">
          <h3>Files</h3>
          <DropZone accept="audio/*,video/*,.mp3,.wav,.m4a,.mp4,.mov" label="Drop audio or video here" hint="MP3, WAV, M4A, or a video. The recording stays on your computer and is not uploaded." onFiles={addFiles} />
          <div className="row">
            <button onClick={() => engine.queue.start()} disabled={pending === 0}>
              Start ({pending})
            </button>
            <button className="secondary" onClick={() => engine.queue.cancelAll()}>
              Cancel all
            </button>
            <button className="secondary" onClick={() => engine.queue.clearFinished()}>
              Clear finished
            </button>
          </div>
        </div>
        <div className="panel stack">
          <h3>Options</h3>
          <label className="field">
            Model
            <select value={t.model} onChange={(e) => set({ model: e.target.value })}>
              {WHISPER_MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} · {m.approxSize}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Language
            <select value={t.language} onChange={(e) => set({ language: e.target.value })}>
              {LANGUAGES.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field inline">
            <input type="checkbox" checked={t.diarize} onChange={(e) => set({ diarize: e.target.checked })} /> Identify speakers (diarization)
          </label>
          {t.diarize && (
            <label className="field">
              Number of speakers (blank = detect)
              <input type="number" min={1} max={20} value={t.numSpeakers ?? ''} onChange={(e) => set({ numSpeakers: e.target.value ? Number(e.target.value) : null })} style={{ width: 90 }} />
            </label>
          )}
        </div>
      </div>
      <div className="panel">
        <h3>Queue</h3>
        <JobTable jobs={jobs} onOpen={openTranscript} />
      </div>
      {viewing && result && (
        <div className="panel stack">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2>{viewing.request.file.name}</h2>
            <div className="row">
              <button onClick={() => save('txt')}>Save .txt</button>
              <button className="secondary" onClick={() => save('srt')}>
                Save .srt
              </button>
              <button className="secondary" onClick={() => save('json')}>
                Save .json
              </button>
              <button className="secondary" onClick={() => setViewing(null)}>
                Close
              </button>
            </div>
          </div>
          {speakerLabels(result).length > 0 && (
            <div className="stack">
              <h3>Who is speaking?</h3>
              <p className="muted small">Type a name for each speaker. The names are used in the transcript below and in every saved file. Click a line to jump to its speaker.</p>
              <div className="row">
                {speakerLabels(result).map((label) => (
                  <label className="field" key={label}>
                    {label}
                    <input
                      type="text"
                      placeholder="Name"
                      value={names[label] ?? ''}
                      ref={(el) => {
                        nameInputs.current[label] = el
                      }}
                      onChange={(e) => setName(label, e.target.value)}
                      style={{ width: 160 }}
                    />
                  </label>
                ))}
              </div>
            </div>
          )}
          <TranscriptView
            result={result}
            names={names}
            onPickSpeaker={(label) => {
              const input = nameInputs.current[label]
              input?.focus()
              input?.select()
            }}
          />
        </div>
      )}
    </>
  )
}

function TranscriptView({ result, names, onPickSpeaker }: { result: TranscriptResult; names: SpeakerNames; onPickSpeaker: (label: string) => void }) {
  if (result.segments.length === 0) return <p>{result.text || 'No speech detected.'}</p>
  return (
    <div className="transcript">
      {result.segments.map((s, i) => (
        <div className={`line ${s.speaker ? 'clickable' : ''}`} key={i} onClick={() => s.speaker && onPickSpeaker(s.speaker)} title={s.speaker ? `Name ${s.speaker}` : undefined}>
          <span className="time">
            {s.start.toFixed(2)}–{s.end.toFixed(2)}
          </span>
          <span className="speaker">{s.speaker ? displayName(s.speaker, names) : ''}</span>
          <span>{s.text}</span>
        </div>
      ))}
    </div>
  )
}

const NAMES_KEY = 'sightline.speakerNames.v1'

function loadSpeakerNames(fileName: string): SpeakerNames {
  try {
    const all = JSON.parse(localStorage.getItem(NAMES_KEY) ?? '{}') as Record<string, SpeakerNames>
    return all[fileName] ?? {}
  } catch {
    return {}
  }
}

function saveSpeakerNames(fileName: string, names: SpeakerNames): void {
  try {
    const all = JSON.parse(localStorage.getItem(NAMES_KEY) ?? '{}') as Record<string, SpeakerNames>
    all[fileName] = names
    localStorage.setItem(NAMES_KEY, JSON.stringify(all))
  } catch {
    // Storage may be blocked; names then last for the session only.
  }
}
