import { SampleReader, type SampleRef, type VideoTrackIndex } from './demux'

export function decoderConfig(track: VideoTrackIndex): VideoDecoderConfig {
  const config: VideoDecoderConfig = { codec: track.codec, codedWidth: track.width, codedHeight: track.height }
  if (track.description) config.description = track.description
  return config
}

export async function assertDecodable(track: VideoTrackIndex): Promise<void> {
  if (typeof VideoDecoder === 'undefined') throw new Error('This browser has no WebCodecs support. Use Chrome, Edge, Safari 16.4+ or Firefox 130+.')
  const support = await VideoDecoder.isConfigSupported(decoderConfig(track))
  if (!support.supported) throw new Error(`This browser cannot decode ${track.codec} video.`)
}

/**
 * Decodes a run of samples in decode order and hands each output frame to
 * `onFrame` in presentation order. Backpressure keeps a handful of frames
 * in flight so memory stays flat on long videos.
 */
export async function decodeSamples(
  track: VideoTrackIndex,
  samples: SampleRef[],
  reader: SampleReader,
  onFrame: (frame: VideoFrame) => Promise<void>,
  signal?: AbortSignal,
): Promise<void> {
  const pending: VideoFrame[] = []
  let decodeError: Error | null = null
  // Producer and consumer each park on their own waiter; sharing one would
  // let a wake-up for one side silently drop the other's.
  const waiters = { producer: null as (() => void) | null, consumer: null as (() => void) | null }
  const wake = () => {
    const { producer, consumer } = waiters
    waiters.producer = null
    waiters.consumer = null
    producer?.()
    consumer?.()
  }
  const parkProducer = () => new Promise<void>((r) => (waiters.producer = r))
  const parkConsumer = () => new Promise<void>((r) => (waiters.consumer = r))
  const decoder = new VideoDecoder({
    output: (frame) => {
      pending.push(frame)
      wake()
    },
    error: (e) => {
      decodeError = e instanceof Error ? e : new Error(String(e))
      wake()
    },
  })
  decoder.configure(decoderConfig(track))

  let consumerDone = false
  let producerDone = false
  const consumer = (async () => {
    while (!consumerDone) {
      if (decodeError) throw decodeError
      const frame = pending.shift()
      if (frame) {
        try {
          await onFrame(frame)
        } finally {
          frame.close()
        }
        wake()
        continue
      }
      if (producerDone) break
      await parkConsumer()
    }
  })()

  try {
    for (const sample of samples) {
      if (signal?.aborted) throw new Error('Cancelled')
      if (decodeError) throw decodeError
      while (decoder.decodeQueueSize > 6 || pending.length > 4) {
        await parkProducer()
        if (decodeError) throw decodeError
      }
      const data = await reader.read(sample)
      decoder.decode(new EncodedVideoChunk({ type: sample.isSync ? 'key' : 'delta', timestamp: sample.cts, duration: sample.duration, data }))
    }
    await decoder.flush()
    producerDone = true
    wake()
    await consumer
  } finally {
    consumerDone = true
    producerDone = true
    wake()
    for (const f of pending) f.close()
    if (decoder.state !== 'closed') decoder.close()
  }
}
