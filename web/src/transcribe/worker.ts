/// <reference lib="webworker" />
import { AutoModel, AutoModelForAudioFrameClassification, AutoProcessor, env, pipeline, type AutomaticSpeechRecognitionPipeline } from '@huggingface/transformers'
import { assignWordSpeakers, clusterEmbeddings, mergeTurns, speakerName, splitSegmentsBySpeaker, wordsToSegments, type WordChunk } from './diarize'
import { EMBEDDING_MODEL, SEGMENTATION_MODEL, type SpeakerTurn, type TranscribeOptions, type TranscriptResult } from './types'
import { TARGET_SAMPLE_RATE } from './audio'
import { ORT_WASM_PATHS } from '../lib/ortPaths'

export type TranscribeWorkerRequest = { type: 'transcribe'; id: string; audio: Float32Array; options: TranscribeOptions; backend: 'webgpu' | 'wasm' }

export type TranscribeWorkerEvent =
  | { type: 'progress'; id: string; fraction: number; message?: string }
  | { type: 'log'; id: string; line: string }
  | { type: 'done'; id: string; result: TranscriptResult }
  | { type: 'error'; id: string; message: string }

const post = (event: TranscribeWorkerEvent) => self.postMessage(event)

env.allowLocalModels = false
env.useBrowserCache = true
// Same ORT build the face detector uses, served from this origin for offline use.
env.backends.onnx.wasm!.wasmPaths = ORT_WASM_PATHS

let asr: { key: string; instance: AutomaticSpeechRecognitionPipeline } | null = null

self.onmessage = async (event: MessageEvent<TranscribeWorkerRequest>) => {
  const { id, audio, options, backend } = event.data
  try {
    const result = await transcribe(id, audio, options, backend)
    post({ type: 'done', id, result })
  } catch (err) {
    post({ type: 'error', id, message: err instanceof Error ? err.message : String(err) })
  }
}

function dtypeFor(model: string, backend: 'webgpu' | 'wasm') {
  if (backend === 'webgpu') {
    return model.includes('large') ? { encoder_model: 'fp16' as const, decoder_model_merged: 'q4' as const } : 'fp32' as const
  }
  return 'q8' as const
}

async function loadAsr(id: string, model: string, backend: 'webgpu' | 'wasm'): Promise<AutomaticSpeechRecognitionPipeline> {
  const key = `${model}|${backend}`
  if (asr?.key === key) return asr.instance
  await asr?.instance.dispose()
  asr = null
  const instance = await pipeline('automatic-speech-recognition', model, {
    device: backend,
    dtype: dtypeFor(model, backend),
    progress_callback: (p: { status: string; file?: string; progress?: number }) => {
      if (p.status === 'progress' && p.file) post({ type: 'progress', id, fraction: 0.02, message: `Downloading ${p.file} ${Math.round(p.progress ?? 0)}%` })
    },
  })
  asr = { key, instance }
  return instance
}

async function transcribe(id: string, audio: Float32Array, options: TranscribeOptions, backend: 'webgpu' | 'wasm'): Promise<TranscriptResult> {
  const durationSeconds = audio.length / TARGET_SAMPLE_RATE
  post({ type: 'progress', id, fraction: 0.02, message: 'Loading Whisper' })
  const transcriber = await loadAsr(id, options.model, backend)
  post({ type: 'log', id, line: `Whisper ${options.model} loaded on ${backend}` })
  post({ type: 'progress', id, fraction: 0.1, message: 'Transcribing' })

  const language = options.language === 'auto' ? undefined : options.language
  let output: { text: string; chunks?: WordChunk[] }
  try {
    output = (await transcriber(audio, { chunk_length_s: 30, stride_length_s: 5, return_timestamps: 'word', language, task: 'transcribe' })) as typeof output
  } catch (err) {
    post({ type: 'log', id, line: `Word timestamps unavailable (${err instanceof Error ? err.message : String(err)}); using segment timestamps.` })
    output = (await transcriber(audio, { chunk_length_s: 30, stride_length_s: 5, return_timestamps: true, language, task: 'transcribe' })) as typeof output
  }
  let segments = wordsToSegments(output.chunks ?? [{ text: output.text, timestamp: [0, durationSeconds] }], durationSeconds)
  post({ type: 'progress', id, fraction: 0.6, message: options.diarize ? 'Finding speakers' : 'Done' })

  let turns: SpeakerTurn[] = []
  let debug: TranscriptResult['debug']
  if (options.diarize) {
    const d = await diarize(id, audio, options.numSpeakers)
    turns = d.turns
    if (options.debug) debug = { rawSegments: d.usable, embeddings: d.embeddings.map((e) => Array.from(e)) }
    segments = splitSegmentsBySpeaker(assignWordSpeakers(turns, segments))
  }
  return {
    language: options.language,
    segments,
    turns,
    text: output.text.trim(),
    durationSeconds,
    model: options.model,
    debug,
  }
}

const WINDOW_SECONDS = 30
const MIN_SEGMENT_SECONDS = 0.6

/**
 * pyannote segmentation gives local speaker turns per 30 s window; WavLM
 * x-vectors plus clustering turn those into global speaker labels.
 */
async function diarize(id: string, audio: Float32Array, numSpeakers: number | null): Promise<{ turns: SpeakerTurn[]; usable: Array<{ start: number; end: number }>; embeddings: Float32Array[] }> {
  const progress = (p: { status: string; file?: string; progress?: number }) => {
    if (p.status === 'progress' && p.file) post({ type: 'progress', id, fraction: 0.6, message: `Downloading ${p.file} ${Math.round(p.progress ?? 0)}%` })
  }
  const segProcessor = await AutoProcessor.from_pretrained(SEGMENTATION_MODEL, { progress_callback: progress })
  const segModel = await AutoModelForAudioFrameClassification.from_pretrained(SEGMENTATION_MODEL, { device: 'wasm', dtype: 'fp32', progress_callback: progress })
  const embProcessor = await AutoProcessor.from_pretrained(EMBEDDING_MODEL, { progress_callback: progress })
  const embModel = await AutoModel.from_pretrained(EMBEDDING_MODEL, { device: 'wasm', dtype: 'fp32', progress_callback: progress })
  post({ type: 'log', id, line: 'Diarization models loaded' })

  const raw: Array<{ start: number; end: number }> = []
  const windowSamples = WINDOW_SECONDS * TARGET_SAMPLE_RATE
  const windows = Math.ceil(audio.length / windowSamples)
  for (let w = 0; w < windows; w++) {
    const offset = w * windowSamples
    const chunk = audio.subarray(offset, Math.min(audio.length, offset + windowSamples))
    if (chunk.length < TARGET_SAMPLE_RATE / 2) continue
    const inputs = await segProcessor(chunk)
    const { logits } = await segModel(inputs)
    const localSegments = (segProcessor as unknown as { post_process_speaker_diarization: (l: unknown, n: number) => Array<Array<{ id: number; start: number; end: number }>> }).post_process_speaker_diarization(logits, chunk.length)[0]
    for (const s of localSegments) {
      // Powerset class 0 is silence; anything else is one or more speakers.
      if (s.id === 0) continue
      raw.push({ start: s.start + offset / TARGET_SAMPLE_RATE, end: s.end + offset / TARGET_SAMPLE_RATE })
    }
    post({ type: 'progress', id, fraction: 0.6 + 0.2 * ((w + 1) / windows), message: `Segmenting speech ${w + 1}/${windows}` })
  }

  const usable = raw.filter((s) => s.end - s.start >= MIN_SEGMENT_SECONDS)
  const embeddings: Float32Array[] = []
  for (let i = 0; i < usable.length; i++) {
    const s = usable[i]
    const slice = audio.subarray(Math.floor(s.start * TARGET_SAMPLE_RATE), Math.floor(s.end * TARGET_SAMPLE_RATE))
    const inputs = await embProcessor(slice)
    const { embeddings: e } = (await embModel(inputs)) as { embeddings: { data: Float32Array } }
    embeddings.push(Float32Array.from(e.data))
    if (i % 5 === 0) post({ type: 'progress', id, fraction: 0.8 + 0.15 * (i / usable.length), message: `Identifying speakers ${i + 1}/${usable.length}` })
  }
  const labels = clusterEmbeddings(embeddings, numSpeakers)
  const turns = usable.map((s, i) => ({ start: s.start, end: s.end, speaker: speakerName(labels[i]) }))
  const merged = mergeTurns(turns)
  post({ type: 'log', id, line: `${new Set(labels).size} speaker(s) found across ${merged.length} turns` })
  return { turns: merged, usable, embeddings }
}
