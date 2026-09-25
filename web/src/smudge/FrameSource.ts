import { decodeSamples, assertDecodable } from '../video/decode'
import { indexMedia, SampleReader, type MediaIndex, type VideoTrackIndex } from '../video/demux'

/**
 * Random access to decoded frames for the editor. A request for frame N
 * decodes from the previous keyframe up to N and fills an LRU cache on the
 * way, which mirrors FrameCache in face_smudge.py.
 */
export class FrameSource {
  readonly track: VideoTrackIndex
  readonly index: MediaIndex
  private cache = new Map<number, ImageBitmap>()
  private reader: SampleReader
  /** Presentation-order sample numbers, since decode order can differ. */
  private presentationOrder: number[]
  private inflight: Promise<void> | null = null

  private cacheSize: number

  private constructor(file: File, index: MediaIndex, cacheSize: number) {
    this.cacheSize = cacheSize
    this.index = index
    this.track = index.video!
    this.reader = new SampleReader(file, 2 * 1024 * 1024)
    this.presentationOrder = this.track.samples
      .map((s, i) => ({ i, cts: s.cts }))
      .sort((a, b) => a.cts - b.cts)
      .map((s) => s.i)
  }

  static async open(file: File, cacheSize = 100): Promise<FrameSource> {
    const index = await indexMedia(file)
    if (!index.video) throw new Error('The file has no video track.')
    await assertDecodable(index.video)
    return new FrameSource(file, index, cacheSize)
  }

  get frameCount(): number {
    return this.track.samples.length
  }

  get fps(): number {
    return this.track.fps
  }

  /** Presentation timestamp in seconds of the Nth displayed frame. */
  timeOf(frame: number): number {
    const sample = this.track.samples[this.presentationOrder[frame]]
    return sample ? sample.cts / 1e6 : 0
  }

  async getFrame(frame: number): Promise<ImageBitmap> {
    const clamped = Math.max(0, Math.min(this.frameCount - 1, frame))
    const hit = this.cache.get(clamped)
    if (hit) {
      this.cache.delete(clamped)
      this.cache.set(clamped, hit)
      return hit
    }
    while (this.inflight) await this.inflight
    const again = this.cache.get(clamped)
    if (again) return again
    this.inflight = this.decodeUpTo(clamped)
    try {
      await this.inflight
    } finally {
      this.inflight = null
    }
    const result = this.cache.get(clamped)
    if (!result) throw new Error(`Frame ${clamped} could not be decoded`)
    return result
  }

  private async decodeUpTo(target: number): Promise<void> {
    const targetSample = this.presentationOrder[target]
    // Walk back in decode order to the nearest keyframe.
    let start = targetSample
    while (start > 0 && !this.track.samples[start].isSync) start -= 1
    // Decode a little past the target so stepping forward stays cached.
    const stop = Math.min(this.track.samples.length, targetSample + Math.min(30, this.cacheSize / 2) + 1)
    const samples = this.track.samples.slice(start, stop)
    const targetCts = this.track.samples[targetSample].cts
    let reached = false
    await decodeSamples(this.track, samples, this.reader, async (vf) => {
      if (reached && vf.timestamp > targetCts + 1_000_000) return
      const frameNumber = this.frameNumberFor(vf.timestamp)
      if (frameNumber < 0) return
      if (!this.cache.has(frameNumber)) {
        const bitmap = await createImageBitmap(vf)
        this.store(frameNumber, bitmap)
      }
      if (frameNumber === target) reached = true
    })
  }

  private frameNumberFor(cts: number): number {
    // Binary search the presentation order for the sample with this cts.
    let lo = 0
    let hi = this.presentationOrder.length - 1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      const c = this.track.samples[this.presentationOrder[mid]].cts
      if (c === cts) return mid
      if (c < cts) lo = mid + 1
      else hi = mid - 1
    }
    return lo < this.presentationOrder.length && Math.abs(this.track.samples[this.presentationOrder[lo]].cts - cts) < 1000 ? lo : -1
  }

  private store(frame: number, bitmap: ImageBitmap): void {
    this.cache.set(frame, bitmap)
    while (this.cache.size > this.cacheSize) {
      const oldest = this.cache.keys().next().value as number
      this.cache.get(oldest)?.close()
      this.cache.delete(oldest)
    }
  }

  close(): void {
    for (const b of this.cache.values()) b.close()
    this.cache.clear()
  }
}
