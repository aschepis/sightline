// Port of scale_bb / draw_det / anonymize_frame from deface/deface.py,
// operating on RGBA ImageData in place.
import type { Detection } from './centerface'
import type { FaceBlurOptions } from './options'

export interface IntBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export function scaleBox(x1: number, y1: number, x2: number, y2: number, maskScale: number): IntBox {
  const s = maskScale - 1.0
  const h = y2 - y1
  const w = x2 - x1
  return {
    x1: Math.round(x1 - w * s),
    y1: Math.round(y1 - h * s),
    x2: Math.round(x2 + w * s),
    y2: Math.round(y2 + h * s),
  }
}

/** numpy astype(int) truncates toward zero. */
function trunc(n: number): number {
  return n < 0 ? Math.ceil(n) : Math.floor(n)
}

export function anonymizeImageData(image: ImageData, dets: Detection[], options: Pick<FaceBlurOptions, 'maskScale' | 'replacewith' | 'boxes' | 'mosaicSize'>): void {
  const H = image.height
  const W = image.width
  for (const det of dets) {
    const scaled = scaleBox(trunc(det.x1), trunc(det.y1), trunc(det.x2), trunc(det.y2), options.maskScale)
    const box: IntBox = {
      y1: Math.max(0, scaled.y1),
      y2: Math.min(H - 1, scaled.y2),
      x1: Math.max(0, scaled.x1),
      x2: Math.min(W - 1, scaled.x2),
    }
    if (box.x2 <= box.x1 || box.y2 <= box.y1) continue
    drawDetection(image, box, options)
  }
}

function drawDetection(image: ImageData, box: IntBox, options: Pick<FaceBlurOptions, 'replacewith' | 'boxes' | 'mosaicSize'>): void {
  switch (options.replacewith) {
    case 'solid':
      fillRect(image, box.x1, box.y1, box.x2, box.y2, [0, 0, 0])
      return
    case 'blur':
      blurBox(image, box, !options.boxes)
      return
    case 'mosaic':
      mosaic(image, box, Math.max(1, options.mosaicSize))
      return
    case 'none':
      return
  }
}

/** cv2.rectangle with thickness -1 is inclusive of both corners. */
function fillRect(image: ImageData, x1: number, y1: number, x2: number, y2: number, rgb: [number, number, number]): void {
  const d = image.data
  const W = image.width
  for (let y = y1; y <= y2; y++) {
    for (let x = x1; x <= x2; x++) {
      const p = (y * W + x) * 4
      d[p] = rgb[0]
      d[p + 1] = rgb[1]
      d[p + 2] = rgb[2]
    }
  }
}

function mosaic(image: ImageData, box: IntBox, size: number): void {
  const d = image.data
  const W = image.width
  for (let y = box.y1; y < box.y2; y += size) {
    for (let x = box.x1; x < box.x2; x += size) {
      const p = (y * W + x) * 4
      fillRect(image, x, y, Math.min(box.x2, x + size - 1), Math.min(box.y2, y + size - 1), [d[p], d[p + 1], d[p + 2]])
    }
  }
}

/**
 * cv2.blur over the region [y1:y2, x1:x2] with kernel (w//2, h//2), then
 * either the whole box or only the inscribed ellipse is written back.
 */
function blurBox(image: ImageData, box: IntBox, ellipse: boolean): void {
  const rw = box.x2 - box.x1
  const rh = box.y2 - box.y1
  const kw = Math.max(1, Math.floor(rw / 2))
  const kh = Math.max(1, Math.floor(rh / 2))
  const blurred = boxBlurRegion(image, box.x1, box.y1, rw, rh, kw, kh)
  const d = image.data
  const W = image.width
  const ry = Math.floor(rh / 2)
  const rx = Math.floor(rw / 2)
  for (let y = 0; y < rh; y++) {
    for (let x = 0; x < rw; x++) {
      if (ellipse) {
        // skimage.draw.ellipse centred at (rh//2, rw//2) with radii (rh//2, rw//2)
        const dy = (y - ry) / Math.max(ry, 1e-6)
        const dx = (x - rx) / Math.max(rx, 1e-6)
        if (dy * dy + dx * dx > 1) continue
      }
      const p = ((box.y1 + y) * W + box.x1 + x) * 4
      const q = (y * rw + x) * 3
      d[p] = blurred[q]
      d[p + 1] = blurred[q + 1]
      d[p + 2] = blurred[q + 2]
    }
  }
}

/**
 * Box blur of a region using a summed-area table. Borders are clamped, which
 * approximates OpenCV's reflected border closely enough for a mask.
 */
export function boxBlurRegion(image: ImageData, x0: number, y0: number, rw: number, rh: number, kw: number, kh: number): Uint8ClampedArray {
  const d = image.data
  const W = image.width
  const sw = rw + 1
  const sat = new Float64Array(sw * (rh + 1) * 3)
  for (let y = 1; y <= rh; y++) {
    let rowR = 0
    let rowG = 0
    let rowB = 0
    for (let x = 1; x <= rw; x++) {
      const p = ((y0 + y - 1) * W + x0 + x - 1) * 4
      rowR += d[p]
      rowG += d[p + 1]
      rowB += d[p + 2]
      const i = (y * sw + x) * 3
      const up = ((y - 1) * sw + x) * 3
      sat[i] = sat[up] + rowR
      sat[i + 1] = sat[up + 1] + rowG
      sat[i + 2] = sat[up + 2] + rowB
    }
  }
  const out = new Uint8ClampedArray(rw * rh * 3)
  const ax = Math.floor(kw / 2)
  const ay = Math.floor(kh / 2)
  for (let y = 0; y < rh; y++) {
    const ya = Math.max(0, y - ay)
    const yb = Math.min(rh, y - ay + kh)
    for (let x = 0; x < rw; x++) {
      const xa = Math.max(0, x - ax)
      const xb = Math.min(rw, x - ax + kw)
      const n = (yb - ya) * (xb - xa)
      const o = (y * rw + x) * 3
      for (let c = 0; c < 3; c++) {
        const sum = sat[(yb * sw + xb) * 3 + c] - sat[(ya * sw + xb) * 3 + c] - sat[(yb * sw + xa) * 3 + c] + sat[(ya * sw + xa) * 3 + c]
        out[o + c] = sum / n
      }
    }
  }
  return out
}
