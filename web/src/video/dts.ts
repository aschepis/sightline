/**
 * Encoders that use B-frames emit chunks in decode order with out-of-order
 * presentation times. MP4 needs a decode time per sample that always
 * increases and never exceeds the presentation time; the difference is
 * stored as the composition offset. Given presentation times in decode
 * order, this returns matching decode times.
 */
export function decodeTimestamps(presentationInDecodeOrder: number[]): number[] {
  const sorted = [...presentationInDecodeOrder].sort((a, b) => a - b)
  let delay = 0
  for (let i = 0; i < sorted.length; i++) {
    delay = Math.max(delay, sorted[i] - presentationInDecodeOrder[i])
  }
  return sorted.map((t) => t - delay)
}
