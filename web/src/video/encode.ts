import { ArrayBufferTarget, Muxer } from 'mp4-muxer'
import type { AudioTrackIndex, SampleReader } from './demux'

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
      video: { codec: picked.mux, width, height, frameRate: fps },
      audio: this.audioMode === 'none' || !audio ? undefined : { codec: this.audioCodec, sampleRate: audio.sampleRate, numberOfChannels: audio.channelCount },
      fastStart: 'in-memory',
      firstTimestampBehavior: 'offset',
    })
    this.encoder = new VideoEncoder({
      output: (chunk, meta) => this.muxer.addVideoChunk(chunk, meta),
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
      let first = true
      for (const sample of audio.samples) {
        if (signal?.aborted) throw new Error('Cancelled')
        const data = await reader.read(sample)
        const meta: EncodedAudioChunkMetadata | undefined = first
          ? { decoderConfig: { codec: audio.codec, sampleRate: audio.sampleRate, numberOfChannels: audio.channelCount, description: audio.description ?? undefined } }
          : undefined
        this.muxer.addAudioChunkRaw(data, 'key', sample.cts, sample.duration, meta)
        first = false
      }
      return
    }
    await this.reencodeAudio(reader, audio, signal)
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

  async finish(): Promise<Blob> {
    await this.encoder.flush()
    if (this.encodeError) throw this.encodeError
    this.encoder.close()
    this.muxer.finalize()
    return new Blob([this.muxer.target.buffer], { type: 'video/mp4' })
  }

  abort(): void {
    if (this.encoder && this.encoder.state !== 'closed') this.encoder.close()
  }
}
