import { createFile, DataStream, MP4BoxBuffer, type ISOFile, type Movie, type Sample } from 'mp4box'
import { displaySize, rotationFromMatrix, type Rotation } from './rotate'

export interface SampleRef {
  number: number
  /** Presentation time in microseconds. */
  cts: number
  /** Decode time in microseconds. */
  dts: number
  /** Duration in microseconds. */
  duration: number
  isSync: boolean
  offset: number
  size: number
}

export interface VideoTrackIndex {
  id: number
  codec: string
  /** Coded frame size, what the decoder emits. */
  width: number
  height: number
  /** Rotation from the track header that players apply on display. */
  rotation: Rotation
  /** Frame size after applying the rotation. */
  displayWidth: number
  displayHeight: number
  fps: number
  durationSeconds: number
  timescale: number
  description: Uint8Array | null
  samples: SampleRef[]
}

export interface AudioTrackIndex {
  id: number
  codec: string
  sampleRate: number
  channelCount: number
  description: Uint8Array | null
  samples: SampleRef[]
}

export interface MediaIndex {
  video: VideoTrackIndex | null
  audio: AudioTrackIndex | null
  durationSeconds: number
}

const READ_CHUNK = 4 * 1024 * 1024

/**
 * Parses an MP4/MOV container and returns per-sample offsets so frames can
 * be read straight from the File, both sequentially and for random access.
 * The mdat payload is never kept in memory.
 */
export async function indexMedia(file: File): Promise<MediaIndex> {
  const mp4 = createFile(false)
  let info: Movie | null = null
  let error: string | null = null
  mp4.onReady = (movie) => {
    info = movie
  }
  mp4.onError = (_module, message) => {
    error = message
  }

  let position = 0
  while (position < file.size) {
    const end = Math.min(file.size, position + READ_CHUNK)
    const buffer = await file.slice(position, end).arrayBuffer()
    const next = mp4.appendBuffer(MP4BoxBuffer.fromArrayBuffer(buffer, position))
    if (error) throw new Error(`Could not parse container: ${error}`)
    if (typeof next !== 'number' || next <= position) {
      position = end
    } else {
      position = next
    }
  }
  mp4.flush()
  if (!info) throw new Error('Unsupported container. Sightline reads MP4, MOV and M4V files in the browser.')
  const movie = info as Movie

  const videoTrack = movie.videoTracks[0]
  const audioTrack = movie.audioTracks[0]
  const video = videoTrack ? buildVideoIndex(mp4, videoTrack) : null
  const audio = audioTrack ? buildAudioIndex(mp4, audioTrack) : null
  if (!video && !audio) throw new Error('No video or audio track found.')
  return { video, audio, durationSeconds: movie.duration / movie.timescale }
}

type TrackInfo = Movie['tracks'][number]

function toSampleRefs(samples: Sample[]): SampleRef[] {
  return samples.map((s) => ({
    number: s.number,
    cts: Math.round((s.cts * 1_000_000) / s.timescale),
    dts: Math.round((s.dts * 1_000_000) / s.timescale),
    duration: Math.round((s.duration * 1_000_000) / s.timescale),
    isSync: s.is_sync,
    offset: s.offset,
    size: s.size,
  }))
}

function buildVideoIndex(mp4: ISOFile, track: TrackInfo): VideoTrackIndex {
  const trak = mp4.getTrackById(track.id)
  const samples = toSampleRefs(trak.samples ?? [])
  const durationSeconds = track.duration / track.timescale
  const fps = samples.length > 1 && durationSeconds > 0 ? samples.length / durationSeconds : 30
  const width = track.video?.width ?? track.track_width
  const height = track.video?.height ?? track.track_height
  const rotation = rotationFromMatrix(track.matrix as unknown as ArrayLike<number> | undefined)
  const display = displaySize(width, height, rotation)
  return {
    id: track.id,
    codec: normalizeCodec(track.codec),
    width,
    height,
    rotation,
    displayWidth: display.width,
    displayHeight: display.height,
    fps,
    durationSeconds,
    timescale: track.timescale,
    description: codecDescription(trak),
    samples,
  }
}

function buildAudioIndex(mp4: ISOFile, track: TrackInfo): AudioTrackIndex {
  const trak = mp4.getTrackById(track.id)
  return {
    id: track.id,
    codec: normalizeCodec(track.codec),
    sampleRate: track.audio?.sample_rate ?? 48000,
    channelCount: track.audio?.channel_count ?? 2,
    description: audioSpecificConfig(trak),
    samples: toSampleRefs(trak.samples ?? []),
  }
}

function normalizeCodec(codec: string): string {
  // mp4box reports e.g. "avc1.64001f"; WebCodecs accepts that directly.
  return codec
}

// The stsd entry holds the codec configuration box (avcC, hvcC, ...). WebCodecs
// wants its payload without the 8-byte box header.
function codecDescription(trak: ReturnType<ISOFile['getTrackById']>): Uint8Array | null {
  const entry = (trak.mdia?.minf?.stbl?.stsd?.entries?.[0] ?? null) as unknown as Record<string, unknown> | null
  if (!entry) return null
  for (const name of ['avcC', 'hvcC', 'vpcC', 'av1C']) {
    const box = entry[name] as { write(stream: unknown): void } | undefined
    if (!box) continue
    const stream = new DataStream()
    box.write(stream)
    return new Uint8Array(stream.buffer as ArrayBuffer, 8)
  }
  return null
}

function audioSpecificConfig(trak: ReturnType<ISOFile['getTrackById']>): Uint8Array | null {
  const entry = (trak.mdia?.minf?.stbl?.stsd?.entries?.[0] ?? null) as unknown as Record<string, unknown> | null
  const esds = entry?.esds as { esd?: { descs?: Array<{ descs?: Array<{ data?: Uint8Array }> }> } } | undefined
  const data = esds?.esd?.descs?.[0]?.descs?.[0]?.data
  return data instanceof Uint8Array ? data : null
}

/**
 * Reads sample payloads from the File with a read-ahead window so that
 * sequential access issues few large reads instead of one per sample.
 */
export class SampleReader {
  private windowStart = 0
  private window: Uint8Array | null = null

  private file: File
  private windowSize: number

  constructor(file: File, windowSize = 8 * 1024 * 1024) {
    this.file = file
    this.windowSize = windowSize
  }

  async read(sample: SampleRef): Promise<Uint8Array> {
    const end = sample.offset + sample.size
    if (!this.window || sample.offset < this.windowStart || end > this.windowStart + this.window.byteLength) {
      const size = Math.max(this.windowSize, sample.size)
      this.windowStart = sample.offset
      this.window = new Uint8Array(await this.file.slice(sample.offset, Math.min(this.file.size, sample.offset + size)).arrayBuffer())
    }
    const start = sample.offset - this.windowStart
    return this.window.slice(start, start + sample.size)
  }
}
