import { describe, expect, it } from 'vitest'
import { decodeDetections, nms, rgbaToTensor, shapeTransform } from '../src/faceblur/centerface'

describe('shapeTransform', () => {
  it('rounds input up to a multiple of 32 like deface', () => {
    const t = shapeTransform(640, 360, 1920, 1080)
    expect(t.wNew).toBe(640)
    expect(t.hNew).toBe(384)
    expect(t.scaleW).toBeCloseTo(640 / 1920)
    expect(t.scaleH).toBeCloseTo(384 / 1080)
  })
})

describe('rgbaToTensor', () => {
  it('produces planar RGB in 0..255', () => {
    const rgba = new Uint8ClampedArray([10, 20, 30, 255, 40, 50, 60, 255])
    const t = rgbaToTensor(rgba, 2, 1)
    expect(Array.from(t)).toEqual([10, 40, 20, 50, 30, 60])
  })
})

describe('decodeDetections', () => {
  it('decodes a single peak into a box the way centerface.py does', () => {
    const fh = 4
    const fw = 4
    const heatmap = new Float32Array(fh * fw)
    const scale = new Float32Array(2 * fh * fw)
    const offset = new Float32Array(2 * fh * fw)
    const idx = 2 * fw + 1 // row 2, col 1
    heatmap[idx] = 0.9
    scale[idx] = Math.log(8 / 4) // height 8
    scale[fh * fw + idx] = Math.log(6 / 4) // width 6
    const dets = decodeDetections({ heatmap, scale, offset, fh, fw }, 16, 16, 0.5)
    expect(dets).toHaveLength(1)
    const d = dets[0]
    expect(d.x1).toBeCloseTo((1 + 0.5) * 4 - 3)
    expect(d.y1).toBeCloseTo((2 + 0.5) * 4 - 4)
    expect(d.x2).toBeCloseTo(d.x1 + 6)
    expect(d.y2).toBeCloseTo(d.y1 + 8)
    expect(d.score).toBeCloseTo(0.9)
  })

  it('suppresses overlapping boxes with lower scores', () => {
    const kept = nms(
      [
        { x1: 0, y1: 0, x2: 10, y2: 10, score: 0.5 },
        { x1: 1, y1: 1, x2: 11, y2: 11, score: 0.9 },
        { x1: 50, y1: 50, x2: 60, y2: 60, score: 0.4 },
      ],
      0.3,
    )
    expect(kept.map((b) => b.score)).toEqual([0.9, 0.4])
  })
})
