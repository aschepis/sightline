import type { FaceBlurOptions } from '../faceblur/options'
import type { SmudgeOperation } from '../smudge/ops'
import type { TranscribeOptions, TranscriptResult } from '../transcribe/types'

export type JobStatus = 'pending' | 'processing' | 'success' | 'failed' | 'cancelled'

export type JobRequest =
  | { kind: 'face-blur'; file: File; options: FaceBlurOptions }
  | { kind: 'smudge-export'; file: File; operations: SmudgeOperation[] }
  | { kind: 'transcribe'; file: File; options: TranscribeOptions }

export type JobOutput =
  | { kind: 'face-blur'; blob: Blob; filename: string; facesDetected: number }
  | { kind: 'smudge-export'; blob: Blob; filename: string }
  | { kind: 'transcribe'; result: TranscriptResult; filename: string }

export interface JobProgress {
  /** 0..1 */
  fraction: number
  message?: string
}

export interface Job {
  id: string
  request: JobRequest
  status: JobStatus
  progress: JobProgress
  log: string[]
  output?: JobOutput
  error?: string
  startedAt?: number
  finishedAt?: number
}

export type Backend = 'webgpu' | 'wasm' | 'remote'

/**
 * An executor runs one job to completion. The browser has a local executor;
 * a remote executor sends the same request to a server running the Python
 * core. Every feature must be implementable on both so nothing depends on
 * browser limits.
 */
export interface Executor {
  readonly name: string
  supports(request: JobRequest): boolean
  run(request: JobRequest, signal: AbortSignal, onProgress: (p: JobProgress) => void, onLog: (line: string) => void): Promise<JobOutput>
}
