import { describe, expect, it } from 'vitest'
import { applySmudge, createOperation, parseOperations, serializeOperations } from '../src/smudge/ops'

function makeImage(w: number, h: number, fill: (x: number, y: number) => number): ImageData {
  const data = new Uint8ClampedArray(w * h * 4)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const p = (y * w + x) * 4
      const v = fill(x, y)
      data[p] = v
      data[p + 1] = v
      data[p + 2] = v
      data[p + 3] = 255
    }
  }
  return { width: w, height: h, data, colorSpace: 'srgb' } as ImageData
}

describe('applySmudge', () => {
  it('blurs inside the circle and leaves the outside alone', () => {
    const img = makeImage(60, 60, (x) => (x < 30 ? 0 : 255))
    const op = createOperation(0, 0.5, 0.5, 10, 4)
    applySmudge(img, op)
    const px = (x: number, y: number) => img.data[(y * 60 + x) * 4]
    expect(px(30, 30)).toBeGreaterThan(20)
    expect(px(30, 30)).toBeLessThan(235)
    expect(px(2, 2)).toBe(0)
    expect(px(58, 58)).toBe(255)
    expect(px(30, 5)).toBe(255)
  })

  it('round-trips through JSON', () => {
    const ops = [createOperation(3, 0.2, 0.4, 50, 25)]
    expect(parseOperations(serializeOperations(ops, 'clip.mp4'))).toEqual(ops)
  })
})
