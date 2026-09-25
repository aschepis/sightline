import { decodeSamples, assertDecodable } from './decode'
import { indexMedia, SampleReader } from './demux'
import { VideoWriter } from './encode'
import { drawUpright } from './rotate'

export interface FrameContext {
  index: number
  total: number
  /** Presentation timestamp in seconds. */
  time: number
  width: number
  height: number
}

export interface ProcessVideoOptions {
  keepAudio: boolean
  /**
   * Mutates the frame's pixels in place. The pipeline hands over an
   * OffscreenCanvas holding the decoded frame plus its ImageData; return
   * true when pixels were changed so the canvas is refreshed from ImageData.
   */
  processFrame: (canvas: OffscreenCanvas, image: ImageData, ctx: FrameContext) => Promise<boolean>
  onProgress?: (fraction: number, message?: string) => void
  log?: (line: string) => void
  signal?: AbortSignal
}

/**
 * Decode -> process -> encode a whole video in the browser, copying audio.
 * This is the shared path for Face Blur and Face Smudge exports.
 */
export async function processVideo(file: File, options: ProcessVideoOptions): Promise<Blob> {
  const index = await indexMedia(file)
  if (!index.video) throw new Error('The file has no video track.')
  const track = index.video
  await assertDecodable(track)
  const reader = new SampleReader(file)
  const width = track.displayWidth
  const height = track.displayHeight
  if (track.rotation !== 0) options.log?.(`Source is rotated ${track.rotation}°; frames are turned upright before processing.`)
  const writer = new VideoWriter({ width, height, fps: track.fps, audio: index.audio, keepAudio: options.keepAudio, log: options.log })
  await writer.open()

  const canvas = new OffscreenCanvas(width, height)
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  const total = track.samples.length
  let processed = 0
  try {
    await decodeSamples(
      track,
      track.samples,
      reader,
      async (frame) => {
        drawUpright(ctx, frame, track.rotation, track.width, track.height)
        const image = ctx.getImageData(0, 0, width, height)
        const changed = await options.processFrame(canvas, image, { index: processed, total, time: frame.timestamp / 1e6, width, height })
        if (changed) ctx.putImageData(image, 0, 0)
        const out = new VideoFrame(canvas, { timestamp: frame.timestamp, duration: frame.duration ?? undefined })
        try {
          await writer.addFrame(out)
        } finally {
          out.close()
        }
        processed += 1
        if (processed % 5 === 0 || processed === total) options.onProgress?.((processed / total) * 0.95, `Frame ${processed} of ${total}`)
      },
      options.signal,
    )
    options.onProgress?.(0.96, 'Writing audio')
    await writer.writeAudio(new SampleReader(file), options.signal)
    options.onProgress?.(0.98, 'Finalizing')
    return await writer.finish()
  } catch (err) {
    writer.abort()
    throw err
  }
}
