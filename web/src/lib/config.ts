import type { FaceBlurOptions } from '../faceblur/options'
import { DEFAULT_FACE_BLUR_OPTIONS } from '../faceblur/options'

export type ExecutionPreference = 'auto' | 'webgpu' | 'wasm' | 'remote'

export interface SmudgeConfig {
  blurRadius: number
  blurSigma: number
  cacheSize: number
  playbackSpeed: number
}

export interface TranscriptionConfig {
  model: string
  language: string
  diarize: boolean
  numSpeakers: number | null
  outputFormat: 'txt' | 'srt' | 'json'
}

export interface AppConfig {
  execution: ExecutionPreference
  batchSize: number
  faceBlur: FaceBlurOptions
  smudge: SmudgeConfig
  transcription: TranscriptionConfig
  remoteEndpoint: string
}

// Mirrors config_manager.get_default_config() in the desktop app.
export const DEFAULT_CONFIG: AppConfig = {
  execution: 'auto',
  batchSize: 2,
  faceBlur: DEFAULT_FACE_BLUR_OPTIONS,
  smudge: { blurRadius: 50, blurSigma: 25, cacheSize: 100, playbackSpeed: 1.0 },
  transcription: {
    model: 'onnx-community/whisper-base_timestamped',
    language: 'auto',
    diarize: true,
    numSpeakers: null,
    outputFormat: 'txt',
  },
  remoteEndpoint: '',
}

const STORAGE_KEY = 'sightline.config.v1'

export function loadConfig(): AppConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return structuredClone(DEFAULT_CONFIG)
    const parsed = JSON.parse(raw) as Partial<AppConfig>
    return {
      ...structuredClone(DEFAULT_CONFIG),
      ...parsed,
      faceBlur: { ...DEFAULT_CONFIG.faceBlur, ...(parsed.faceBlur ?? {}) },
      smudge: { ...DEFAULT_CONFIG.smudge, ...(parsed.smudge ?? {}) },
      transcription: { ...DEFAULT_CONFIG.transcription, ...(parsed.transcription ?? {}) },
    }
  } catch {
    return structuredClone(DEFAULT_CONFIG)
  }
}

export function saveConfig(config: AppConfig): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  } catch {
    // Private windows and blocked storage fall back to in-memory config.
  }
}
