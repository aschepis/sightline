import { ArrayBufferTarget, Muxer } from 'mp4-muxer'
import type { AudioTrackIndex, SampleReader } from './demux'
import { decodeTimestamps } from './dts'

type MuxCodec = 'avc' | 'hevc' | 'vp9' | 'av1'

const VIDEO_CANDIDATES: Array<{ codec: string; mux: MuxCodec; maxPixels: number }> = [
  { codec: 'avc1.640028', mux: 'avc', maxPixels: 1920 * 1088 },
  { codec: 'avc1.640033', mux: 'avc', maxPixels: 4096 * 2304 },
  { codec: 'avc1.64003C', mux: 'avc', maxPixels: 8192 * 4320 },
  { codec: 'vp09.00.51.08', mux: 'vp9', maxPixels: 8192 * 4320 },
  { codec: 'av01.0.13M.08', mux: 'av1', maxPixels: 8192 * 4320 },
]

export interface WriterOptions {
  width: number
  height: number
  fps: number
  audio: AudioTrackIndex | null
  keepAudio: boolean
  log?: (line: string) => void
}

export async function pickVideoCodec(width: number, height: number, fps: number): Promise<{ codec: string; mux: MuxCodec; bitrate: number }> {
  const pixels = width * height
  const bitrate = Math.min(60_000_000, Math.max(1_000_000, Math.round(pixels * fps * 0.12)))
  for (const candidate of VIDEO_CANDIDATES) {
    if (pixels > candidate.maxPixels) continue
    const config: VideoEncoderConfig = { codec: candidate.codec, width, height, bitrate, framerate: fps }
    if (candidate.mux === 'avc') config.avc = { format: 'avc' }
    try {
      const support = await VideoEncoder.isConfigSupported(config)
      if (support.supported) return { codec: candidate.codec, mux: candidate.mux, bitrate }
    } catch {
      // try the next candidate
    }
  }
  throw new Error('No supported video encoder found in this browser.')
}

/**
 * Encodes processed frames into an MP4, copying the source audio track when
 * possible and re-encoding it otherwise. Mirrors deface's keep_audio and the
 * ffmpeg remux step of the smudge exporter.
 */
export class VideoWriter {
  private muxer!: Muxer<ArrayBufferTarget>
  private encoder!: VideoEncoder
  private encodeError: Error | null = null
  private frameCount = 0
  // Encoded chunks are held until finish() so decode times can be derived
  // once the encoder's reorder delay is known (see dts.ts).
  private chunks: Array<{ data: Uint8Array; type: 'key' | 'delta'; timestamp: number; duration: number; meta?: EncodedVideoChunkMetadata }> = []
  private audioMode: 'copy' | 'reencode' | 'none' = 'none'
  private audioCodec: 'aac' | 'opus' = 'aac'

  private options: WriterOptions

  constructor(options: WriterOptions) {
    this.options = options
  }

  async open(): Promise<void> {
    const { width, height, fps, audio, keepAudio } = this.options
    const picked = await pickVideoCodec(width, height, fps)
    this.audioMode = keepAudio && audio ? await this.chooseAudioMode(audio) : 'none'
    this.muxer = new Muxer({
      target: new ArrayBufferTarget(),
      // mp4-muxer wants an integer here; real per-frame timestamps still carry the true rate.
      video: { codec: picked.mux, width, height, frameRate: Math.max(1, Math.round(fps)) },
      audio: this.audioMode === 'none' || !audio ? undefined : { codec: this.audioCodec, sampleRate: audio.sampleRate, numberOfChannels: audio.channelCount },
      fastStart: 'in-memory',
      firstTimestampBehavior: 'offset',
    })
    this.encoder = new VideoEncoder({
      output: (chunk, meta) => {
        const data = new Uint8Array(chunk.byteLength)
        chunk.copyTo(data)
        this.chunks.push({ data, type: chunk.type, timestamp: chunk.timestamp, duration: chunk.duration ?? 0, meta })
      },
      error: (e) => {
        this.encodeError = e instanceof Error ? e : new Error(String(e))
      },
    })
    const config: VideoEncoderConfig = { codec: picked.codec, width, height, bitrate: picked.bitrate, framerate: fps, latencyMode: 'quality' }
    if (picked.mux === 'avc') config.avc = { format: 'avc' }
    this.encoder.configure(config)
    this.options.log?.(`Encoding ${width}x${height} @ ${fps.toFixed(2)} fps with ${picked.codec}, audio: ${this.audioMode}`)
  }

  private async chooseAudioMode(audio: AudioTrackIndex): Promise<'copy' | 'reencode' | 'none'> {
    if (audio.codec.startsWith('mp4a.40')) {
      this.audioCodec = 'aac'
      return 'copy'
    }
    if (audio.codec === 'opus' || audio.codec.startsWith('Opus')) {
      this.audioCodec = 'opus'
      return 'copy'
    }
    if (typeof AudioDecoder === 'undefined' || typeof AudioEncoder === 'undefined') return 'none'
    for (const candidate of ['mp4a.40.2', 'opus'] as const) {
      try {
        const support = await AudioEncoder.isConfigSupported({ codec: candidate, sampleRate: audio.sampleRate, numberOfChannels: audio.channelCount, bitrate: 128_000 })
        if (support.supported) {
          this.audioCodec = candidate === 'opus' ? 'opus' : 'aac'
          return 'reencode'
        }
      } catch {
        // try next
      }
    }
    this.options.log?.(`Audio codec ${audio.codec} cannot be copied or re-encoded here; output will be silent.`)
    return 'none'
  }

  async addFrame(frame: VideoFrame): Promise<void> {
    if (this.encodeError) throw this.encodeError
    while (this.encoder.encodeQueueSize > 8) {
      await new Promise((r) => setTimeout(r, 5))
      if (this.encodeError) throw this.encodeError
    }
    // A keyframe every ~2 seconds keeps seeking usable in players.
    const keyFrame = this.frameCount % Math.max(1, Math.round(this.options.fps * 2)) === 0
    this.encoder.encode(frame, { keyFrame })
    this.frameCount += 1
  }

  async writeAudio(reader: SampleReader, signal?: AbortSignal): Promise<void> {
    const audio = this.options.audio
    if (!audio || this.audioMode === 'none') return
    if (this.audioMode === 'copy') {
      const description = audio.description ?? (this.audioCodec === 'aac' ? aacAudioSpecificConfig(audio.sampleRate, audio.channelCount) : undefined)
      let first = true
      for (const sample of audio.samples) {
        if (signal?.aborted) throw new Error('Cancelled')
        const data = await reader.read(sample)
        const meta: EncodedAudioChunkMetadata | undefined = first
          ? { decoderConfig: { codec: audio.codec, sampleRate: audio.sampleRate, numberOfChannels: audio.channelCount, description } }
          : undefined
        this.muxer.addAudioChunkRaw(data, 'key', sample.cts, sample.duration, meta)
        first = false
      }
      this.options.log?.(`Audio: copied ${audio.samples.length} ${audio.codec} chunks${audio.description ? '' : ' (synthesized AAC config)'}`)
      return
    }
    await this.reencodeAudio(reader, audio, signal)
    this.options.log?.(`Audio: re-encoded ${audio.codec} to ${this.audioCodec}`)
  }

  private async reencodeAudio(reader: SampleReader, audio: AudioTrackIndex, signal?: AbortSignal): Promise<void> {
    const codec = this.audioCodec === 'aac' ? 'mp4a.40.2' : 'opus'
    let failure: Error | null = null
    const encoder = new AudioEncoder({
      output: (chunk, meta) => this.muxer.addAudioChunk(chunk, meta),
      error: (e) => {
        failure = e instanceof Error ? e : new Error(String(e))
      },
    })
    encoder.configure({ codec, sampleRate: audio.sampleRate, numberOfChannels: audio.channelCount, bitrate: 128_000 })
    const decoder = new AudioDecoder({
      output: (data) => {
        encoder.encode(data)
        data.close()
      },
      error: (e) => {
        failure = e instanceof Error ? e : new Error(String(e))
      },
    })
    decoder.configure({ codec: audio.codec, sampleRate: audio.sampleRate, numberOfChannels: audio.channelCount, description: audio.description ?? undefined })
    for (const sample of audio.samples) {
      if (signal?.aborted) throw new Error('Cancelled')
      if (failure) throw failure
      while (decoder.decodeQueueSize > 16) await new Promise((r) => setTimeout(r, 5))
      const data = await reader.read(sample)
      decoder.decode(new EncodedAudioChunk({ type: sample.isSync ? 'key' : 'delta', timestamp: sample.cts, duration: sample.duration, data }))
    }
    await decoder.flush()
    await encoder.flush()
    decoder.close()
    encoder.close()
    if (failure) throw failure
  }

  /** Flushes the encoder and writes the video track; call before writeAudio(). */
  async finishVideo(): Promise<void> {
    if (this.encoder.state === 'closed') return
    await this.encoder.flush()
    if (this.encodeError) throw this.encodeError
    this.encoder.close()
    this.writeVideoChunks()
  }

  async finish(): Promise<Blob> {
    await this.finishVideo()
    this.muxer.finalize()
    return new Blob([this.muxer.target.buffer], { type: 'video/mp4' })
  }

  private writeVideoChunks(): void {
    const dts = decodeTimestamps(this.chunks.map((c) => c.timestamp))
    let reordered = 0
    this.chunks.forEach((c, i) => {
      const offset = c.timestamp - dts[i]
      if (offset !== 0) reordered += 1
      this.muxer.addVideoChunkRaw(c.data, c.type, c.timestamp, c.duration, i === 0 ? c.meta : undefined, offset)
    })
    if (reordered > 0) this.options.log?.(`Encoder used B-frames; wrote decode times for ${reordered} reordered chunks`)
    this.chunks = []
  }

  abort(): void {
    if (this.encoder && this.encoder.state !== 'closed') this.encoder.close()
  }
}

const AAC_SAMPLE_RATES = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350]

/** Two-byte AudioSpecificConfig for AAC-LC, used when the container lacks an esds payload. */
export function aacAudioSpecificConfig(sampleRate: number, channels: number): Uint8Array {
  let index = AAC_SAMPLE_RATES.indexOf(sampleRate)
  if (index < 0) index = 4
  const objectType = 2
  const bits = (objectType << 11) | (index << 7) | (Math.min(7, channels) << 3)
  return new Uint8Array([(bits >> 8) & 0xff, bits & 0xff])
}
