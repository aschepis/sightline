import { describe, expect, it } from 'vitest'
import { decodeTimestamps } from '../src/video/dts'

describe('decodeTimestamps', () => {
  it('leaves in-order chunks alone', () => {
    expect(decodeTimestamps([0, 33, 66, 100])).toEqual([0, 33, 66, 100])
  })

  it('derives increasing decode times for B-frame order', () => {
    // Decode order I P B B: presentation 0, 100, 33, 66.
    const pts = [0, 100, 33, 66]
    const dts = decodeTimestamps(pts)
    for (let i = 1; i < dts.length; i++) expect(dts[i]).toBeGreaterThan(dts[i - 1])
    for (let i = 0; i < dts.length; i++) expect(dts[i]).toBeLessThanOrEqual(pts[i])
    expect(dts).toEqual([-34, -1, 32, 66])
  })

  it('handles the reported sequence', () => {
    const pts = [0, 33333, 100000, 66667]
    const dts = decodeTimestamps(pts)
    expect(dts).toEqual([-33333, 0, 33334, 66667])
  })
})
