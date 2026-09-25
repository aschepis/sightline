import { describe, expect, it } from 'vitest'
import { anonymizeImageData, boxBlurRegion, scaleBox } from '../src/faceblur/anonymize'

function makeImage(w: number, h: number, fill: (x: number, y: number) => [number, number, number]): ImageData {
  const data = new Uint8ClampedArray(w * h * 4)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [r, g, b] = fill(x, y)
      const p = (y * w + x) * 4
      data[p] = r
      data[p + 1] = g
      data[p + 2] = b
      data[p + 3] = 255
    }
  }
  return { width: w, height: h, data, colorSpace: 'srgb' } as ImageData
}

describe('scaleBox', () => {
  it('grows the box by mask_scale - 1 on each side like deface.scale_bb', () => {
    expect(scaleBox(10, 20, 30, 60, 1.3)).toEqual({ x1: 4, y1: 8, x2: 36, y2: 72 })
  })
})

describe('anonymizeImageData', () => {
  it('fills a solid black rectangle inclusive of the far edge', () => {
    const img = makeImage(20, 20, () => [200, 200, 200])
    anonymizeImageData(img, [{ x1: 5, y1: 5, x2: 10, y2: 10, score: 1 }], { maskScale: 1, replacewith: 'solid', boxes: true, mosaicSize: 20 })
    const px = (x: number, y: number) => img.data[(y * 20 + x) * 4]
    expect(px(5, 5)).toBe(0)
    expect(px(10, 10)).toBe(0)
    expect(px(11, 11)).toBe(200)
    expect(px(4, 4)).toBe(200)
  })

  it('blurs only the inscribed ellipse when boxes is false', () => {
    const img = makeImage(40, 40, (x) => (x < 20 ? [0, 0, 0] : [255, 255, 255]))
    anonymizeImageData(img, [{ x1: 10, y1: 10, x2: 30, y2: 30, score: 1 }], { maskScale: 1, replacewith: 'blur', boxes: false, mosaicSize: 20 })
    const px = (x: number, y: number) => img.data[(y * 40 + x) * 4]
    // Centre of the ellipse straddles the black/white edge, so it becomes grey.
    expect(px(20, 20)).toBeGreaterThan(40)
    expect(px(20, 20)).toBeLessThan(215)
    // Corners of the box are outside the ellipse and stay untouched.
    expect(px(10, 10)).toBe(0)
    expect(px(29, 29)).toBe(255)
  })

  it('mosaic uses the top-left pixel of each block', () => {
    const img = makeImage(10, 10, (x, y) => [x * 10, y * 10, 0])
    anonymizeImageData(img, [{ x1: 0, y1: 0, x2: 9, y2: 9, score: 1 }], { maskScale: 1, replacewith: 'mosaic', boxes: true, mosaicSize: 5 })
    const px = (x: number, y: number) => img.data[(y * 10 + x) * 4]
    expect(px(4, 4)).toBe(0)
    expect(px(5, 5)).toBe(50)
    expect(px(9, 9)).toBe(50)
  })
})

describe('boxBlurRegion', () => {
  it('averages a flat region to itself', () => {
    const img = makeImage(8, 8, () => [100, 150, 200])
    const out = boxBlurRegion(img, 0, 0, 8, 8, 4, 4)
    expect(out[0]).toBe(100)
    expect(out[1]).toBe(150)
    expect(out[2]).toBe(200)
  })
})
