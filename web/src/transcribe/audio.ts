export const TARGET_SAMPLE_RATE = 16_000

/**
 * Decodes any audio or video file the browser understands into 16 kHz mono
 * PCM, which is what Whisper and pyannote expect. Runs on the main thread
 * because AudioContext is unavailable in workers.
 */
export async function decodeToMono16k(file: File): Promise<Float32Array> {
  const bytes = await file.arrayBuffer()
  const probe = new AudioContext()
  let decoded: AudioBuffer
  try {
    decoded = await probe.decodeAudioData(bytes)
  } finally {
    await probe.close()
  }
  const length = Math.ceil((decoded.duration * TARGET_SAMPLE_RATE) / 1) + 1
  const offline = new OfflineAudioContext(1, length, TARGET_SAMPLE_RATE)
  const source = offline.createBufferSource()
  source.buffer = decoded
  source.connect(offline.destination)
  source.start(0)
  const rendered = await offline.startRendering()
  return rendered.getChannelData(0).slice(0, Math.floor(decoded.duration * TARGET_SAMPLE_RATE))
}
