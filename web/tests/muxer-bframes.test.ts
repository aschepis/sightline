import { ArrayBufferTarget, Muxer } from 'mp4-muxer'
import { describe, expect, it } from 'vitest'
import { decodeTimestamps } from '../src/video/dts'

// Reproduces the reported "DTS went from 100000 to 66667" sequence against
// the real muxer, using the composition offsets the writer now supplies.
describe('mp4-muxer with B-frame chunk order', () => {
  const pts = [0, 33333, 100000, 66667, 133333]
  const fakeAvcC = new Uint8Array([1, 0x64, 0, 0x28, 0xff, 0xe1, 0, 0, 1, 0, 0])

  function mux(withOffsets: boolean) {
    const muxer = new Muxer({
      target: new ArrayBufferTarget(),
      video: { codec: 'avc', width: 16, height: 16, frameRate: 30 },
      fastStart: 'in-memory',
      firstTimestampBehavior: 'offset',
    })
    const dts = decodeTimestamps(pts)
    pts.forEach((t, i) => {
      const meta = i === 0 ? { decoderConfig: { codec: 'avc1.640028', description: fakeAvcC } } : undefined
      muxer.addVideoChunkRaw(new Uint8Array([0, 0, 0, 1, 0x65]), i === 0 ? 'key' : 'delta', t, 33333, meta, withOffsets ? t - dts[i] : undefined)
    })
    muxer.finalize()
    return muxer.target.buffer
  }

  it('fails without composition offsets, as reported', () => {
    expect(() => mux(false)).toThrow(/monotonically increasing/)
  })

  it('succeeds with derived decode times and writes a ctts box', () => {
    const buffer = mux(true)
    const text = new TextDecoder('latin1').decode(new Uint8Array(buffer))
    expect(text).toContain('ctts')
    expect(buffer.byteLength).toBeGreaterThan(500)
  })
})
