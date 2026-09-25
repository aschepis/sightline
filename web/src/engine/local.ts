import type { Capabilities } from '../lib/capabilities'
import type { ExecutionPreference } from '../lib/config'
import { outputFilename } from '../lib/files'
import type { MediaWorkerEvent, MediaWorkerRequest } from '../faceblur/worker'
import { decodeToMono16k } from '../transcribe/audio'
import type { TranscribeWorkerEvent, TranscribeWorkerRequest } from '../transcribe/worker'
import type { Backend, Executor, JobOutput, JobProgress, JobRequest } from './types'

export function chooseBackend(preference: ExecutionPreference, caps: Capabilities): Backend {
  if (preference === 'remote') return 'remote'
  if (preference === 'wasm') return 'wasm'
  return caps.webgpu ? 'webgpu' : 'wasm'
}

/**
 * Runs jobs in Web Workers on this device. Face blur and smudge exports get
 * a fresh worker per job so cancelling is a plain terminate(); transcription
 * keeps one worker alive because its models take seconds to load.
 */
export class LocalExecutor implements Executor {
  readonly name = 'local'
  private transcribeWorker: Worker | null = null

  private backend: Exclude<Backend, 'remote'>

  constructor(backend: Exclude<Backend, 'remote'>) {
    this.backend = backend
  }

  setBackend(backend: Exclude<Backend, 'remote'>): void {
    if (backend !== this.backend) {
      this.backend = backend
      this.transcribeWorker?.terminate()
      this.transcribeWorker = null
    }
  }

  supports(): boolean {
    return true
  }

  async run(request: JobRequest, signal: AbortSignal, onProgress: (p: JobProgress) => void, onLog: (line: string) => void): Promise<JobOutput> {
    switch (request.kind) {
      case 'face-blur':
      case 'smudge-export':
        return this.runMedia(request, signal, onProgress, onLog)
      case 'transcribe':
        return this.runTranscribe(request, signal, onProgress, onLog)
    }
  }

  private runMedia(request: Extract<JobRequest, { kind: 'face-blur' | 'smudge-export' }>, signal: AbortSignal, onProgress: (p: JobProgress) => void, onLog: (line: string) => void): Promise<JobOutput> {
    const worker = new Worker(new URL('../faceblur/worker.ts', import.meta.url), { type: 'module' })
    const id = crypto.randomUUID()
    return new Promise<JobOutput>((resolve, reject) => {
      const finish = () => worker.terminate()
      signal.addEventListener('abort', () => {
        finish()
        reject(new Error('Cancelled'))
      })
      worker.onerror = (e) => {
        finish()
        reject(new Error(e.message || 'Worker crashed'))
      }
      worker.onmessage = (event: MessageEvent<MediaWorkerEvent>) => {
        const msg = event.data
        if (msg.id !== id) return
        if (msg.type === 'progress') onProgress({ fraction: msg.fraction, message: msg.message })
        else if (msg.type === 'log') onLog(msg.line)
        else if (msg.type === 'error') {
          finish()
          reject(new Error(msg.message))
        } else if (msg.type === 'done') {
          finish()
          if (request.kind === 'face-blur') {
            resolve({ kind: 'face-blur', blob: msg.blob, filename: outputFilename(request.file.name, '_anonymized', videoExt(request.file, msg.blob)), facesDetected: msg.facesDetected })
          } else {
            resolve({ kind: 'smudge-export', blob: msg.blob, filename: outputFilename(request.file.name, '_smudged', '.mp4') })
          }
        }
      }
      const message: MediaWorkerRequest =
        request.kind === 'face-blur'
          ? { type: 'face-blur', id, file: request.file, options: request.options, backend: this.backend }
          : { type: 'smudge-export', id, file: request.file, operations: request.operations }
      worker.postMessage(message)
    })
  }

  private async runTranscribe(request: Extract<JobRequest, { kind: 'transcribe' }>, signal: AbortSignal, onProgress: (p: JobProgress) => void, onLog: (line: string) => void): Promise<JobOutput> {
    onProgress({ fraction: 0.01, message: 'Decoding audio' })
    const audio = await decodeToMono16k(request.file)
    if (signal.aborted) throw new Error('Cancelled')
    onLog(`Decoded ${(audio.length / 16000).toFixed(1)} s of audio`)
    const worker = this.transcribeWorker ?? new Worker(new URL('../transcribe/worker.ts', import.meta.url), { type: 'module' })
    this.transcribeWorker = worker
    const id = crypto.randomUUID()
    return new Promise<JobOutput>((resolve, reject) => {
      const cleanup = () => {
        worker.onmessage = null
        worker.onerror = null
      }
      signal.addEventListener('abort', () => {
        // Terminating drops the loaded models; the next job reloads them.
        worker.terminate()
        this.transcribeWorker = null
        cleanup()
        reject(new Error('Cancelled'))
      })
      worker.onerror = (e) => {
        this.transcribeWorker = null
        cleanup()
        reject(new Error(e.message || 'Worker crashed'))
      }
      worker.onmessage = (event: MessageEvent<TranscribeWorkerEvent>) => {
        const msg = event.data
        if (msg.id !== id) return
        if (msg.type === 'progress') onProgress({ fraction: msg.fraction, message: msg.message })
        else if (msg.type === 'log') onLog(msg.line)
        else if (msg.type === 'error') {
          cleanup()
          reject(new Error(msg.message))
        } else if (msg.type === 'done') {
          cleanup()
          resolve({ kind: 'transcribe', result: msg.result, filename: outputFilename(request.file.name, '_transcript', '.txt') })
        }
      }
      const message: TranscribeWorkerRequest = { type: 'transcribe', id, audio, options: request.options, backend: this.backend }
      worker.postMessage(message, [audio.buffer])
    })
  }
}

function videoExt(file: File, blob: Blob): string | undefined {
  if (blob.type === 'video/mp4') return '.mp4'
  if (blob.type === 'image/png' && !/\.png$/i.test(file.name)) return '.png'
  return undefined
}
