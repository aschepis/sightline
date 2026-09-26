export interface TranscribeOptions {
  model: string
  /** ISO code such as "en", or "auto". */
  language: string
  diarize: boolean
  numSpeakers: number | null
  /** Development only: include raw diarization data in the result. */
  debug?: boolean
}

export interface Word {
  text: string
  start: number
  end: number
  speaker?: string
}

export interface Segment {
  start: number
  end: number
  text: string
  speaker?: string
  words: Word[]
}

export interface SpeakerTurn {
  start: number
  end: number
  speaker: string
}

export interface TranscriptResult {
  language: string
  segments: Segment[]
  turns: SpeakerTurn[]
  text: string
  durationSeconds: number
  model: string
  debug?: { rawSegments: Array<{ start: number; end: number }>; embeddings: number[][] }
}

export interface WhisperModelChoice {
  id: string
  label: string
  approxSize: string
  multilingual: boolean
}

// The _timestamped exports include cross-attention outputs, which is what
// gives word-level timestamps for speaker assignment. Sizes are the WebGPU
// (fp32) downloads measured in Chrome; the WebAssembly q8 files are about a third.
export const WHISPER_MODELS: WhisperModelChoice[] = [
  { id: 'onnx-community/whisper-tiny_timestamped', label: 'Whisper tiny (fastest)', approxSize: '~150 MB', multilingual: true },
  { id: 'onnx-community/whisper-base_timestamped', label: 'Whisper base (desktop default)', approxSize: '~280 MB', multilingual: true },
  { id: 'onnx-community/whisper-small_timestamped', label: 'Whisper small', approxSize: '~950 MB', multilingual: true },
  { id: 'onnx-community/whisper-large-v3-turbo_timestamped', label: 'Whisper large-v3 turbo (best, WebGPU)', approxSize: '~800 MB', multilingual: true },
]

export const SEGMENTATION_MODEL = 'onnx-community/pyannote-segmentation-3.0'
export const EMBEDDING_MODEL = 'Xenova/wavlm-base-plus-sv'
