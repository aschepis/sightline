/// <reference lib="webworker" />
import { anonymizeImageData } from './anonymize'
import { FaceDetector, type DetectorBackend } from './detector'
import { copyJpegExif } from './exif'
import type { FaceBlurOptions } from './options'
import { applyOperations, type SmudgeOperation } from '../smudge/ops'
import { processVideo } from '../video/pipeline'

export type MediaWorkerRequest =
  | { type: 'face-blur'; id: string; file: File; options: FaceBlurOptions; backend: DetectorBackend }
  | { type: 'smudge-export'; id: string; file: File; operations: SmudgeOperation[] }
  | { type: 'cancel'; id: string }

export type MediaWorkerEvent =
  | { type: 'progress'; id: string; fraction: number; message?: string }
  | { type: 'log'; id: string; line: string }
  | { type: 'done'; id: string; blob: Blob; facesDetected: number }
  | { type: 'error'; id: string; message: string }

const cancelled = new Set<string>()
const post = (event: MediaWorkerEvent) => self.postMessage(event)

self.onmessage = async (event: MessageEvent<MediaWorkerRequest>) => {
  const msg = event.data
  if (msg.type === 'cancel') {
    cancelled.add(msg.id)
    return
  }
  const controller = new AbortController()
  const watch = setInterval(() => {
    if (cancelled.has(msg.id)) controller.abort()
  }, 100)
  try {
    if (msg.type === 'face-blur') await runFaceBlur(msg, controller.signal)
    else await runSmudgeExport(msg, controller.signal)
  } catch (err) {
    post({ type: 'error', id: msg.id, message: err instanceof Error ? err.message : String(err) })
  } finally {
    clearInterval(watch)
  }
}

async function runFaceBlur(msg: Extract<MediaWorkerRequest, { type: 'face-blur' }>, signal: AbortSignal): Promise<void> {
  const { id, file, options } = msg
  const detector = new FaceDetector(msg.backend)
  post({ type: 'progress', id, fraction: 0.01, message: 'Loading detector' })
  await detector.load((loaded, total) => post({ type: 'progress', id, fraction: 0.01, message: `Downloading model ${Math.round((loaded / Math.max(total, 1)) * 100)}%` }))
  post({ type: 'log', id, line: `CenterFace ready on ${msg.backend}` })

  const isImage = file.type.startsWith('image/') || /\.(jpe?g|png|bmp|webp|tiff?)$/i.test(file.name)
  let faces = 0
  if (isImage) {
    const bitmap = await createImageBitmap(file)
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!
    ctx.drawImage(bitmap, 0, 0)
    const dets = await detector.detect(bitmap, bitmap.width, bitmap.height, options.scale, options.thresh)
    bitmap.close()
    faces = dets.length
    const image = ctx.getImageData(0, 0, canvas.width, canvas.height)
    anonymizeImageData(image, dets, options)
    ctx.putImageData(image, 0, 0)
    const isJpeg = /jpe?g/i.test(file.type) || /\.jpe?g$/i.test(file.name)
    let blob = await canvas.convertToBlob(isJpeg ? { type: 'image/jpeg', quality: 0.92 } : { type: 'image/png' })
    if (isJpeg && options.keepMetadata) {
      const merged = copyJpegExif(new Uint8Array(await file.arrayBuffer()), new Uint8Array(await blob.arrayBuffer()))
      blob = new Blob([merged as Uint8Array<ArrayBuffer>], { type: 'image/jpeg' })
    }
    post({ type: 'log', id, line: `${faces} face(s) detected` })
    post({ type: 'done', id, blob, facesDetected: faces })
    return
  }

  if (options.keepMetadata) post({ type: 'log', id, line: 'Container metadata is not carried over for video in the browser yet.' })
  const blob = await processVideo(file, {
    keepAudio: options.keepAudio,
    signal,
    log: (line) => post({ type: 'log', id, line }),
    onProgress: (fraction, message) => post({ type: 'progress', id, fraction, message }),
    processFrame: async (canvas, image, ctx) => {
      const dets = await detector.detect(canvas, ctx.width, ctx.height, options.scale, options.thresh)
      faces += dets.length
      if (dets.length === 0) return false
      anonymizeImageData(image, dets, options)
      return true
    },
  })
  await detector.dispose()
  post({ type: 'log', id, line: `${faces} face detections across all frames` })
  post({ type: 'done', id, blob, facesDetected: faces })
}

async function runSmudgeExport(msg: Extract<MediaWorkerRequest, { type: 'smudge-export' }>, signal: AbortSignal): Promise<void> {
  const { id, file, operations } = msg
  const byFrame = new Map<number, SmudgeOperation[]>()
  for (const op of operations) {
    const list = byFrame.get(op.frame) ?? []
    list.push(op)
    byFrame.set(op.frame, list)
  }
  const blob = await processVideo(file, {
    keepAudio: true,
    signal,
    log: (line) => post({ type: 'log', id, line }),
    onProgress: (fraction, message) => post({ type: 'progress', id, fraction, message }),
    processFrame: async (_canvas, image, ctx) => applyOperations(image, byFrame.get(ctx.index) ?? []),
  })
  post({ type: 'done', id, blob, facesDetected: 0 })
}
