// Port of SmudgeOperation, create_circular_mask and apply_smudge_to_frame
// from face_smudge.py, operating on RGBA ImageData.

export interface SmudgeOperation {
  id: string
  frame: number
  /** Centre X, 0..1 of frame width. */
  x: number
  /** Centre Y, 0..1 of frame height. */
  y: number
  /** Radius in frame pixels. */
  radius: number
  /** Gaussian sigma in pixels. */
  sigma: number
  timestamp: number
}

export function createOperation(frame: number, x: number, y: number, radius: number, sigma: number): SmudgeOperation {
  return { id: crypto.randomUUID(), frame, x, y, radius, sigma, timestamp: Date.now() }
}

export function applySmudge(image: ImageData, op: SmudgeOperation): void {
  const W = image.width
  const H = image.height
  const cx = Math.trunc(op.x * W)
  const cy = Math.trunc(op.y * H)
  const r = op.radius
  const yMin = Math.max(0, cy - r)
  const yMax = Math.min(H, cy + r + 1)
  const xMin = Math.max(0, cx - r)
  const xMax = Math.min(W, cx + r + 1)
  const rw = xMax - xMin
  const rh = yMax - yMin
  if (rw <= 0 || rh <= 0) return

  const blurred = gaussianBlurRegion(image, xMin, yMin, rw, rh, op.sigma)
  const d = image.data
  const r2 = r * r
  for (let y = 0; y < rh; y++) {
    const dy = yMin + y - cy
    for (let x = 0; x < rw; x++) {
      const dx = xMin + x - cx
      if (dx * dx + dy * dy > r2) continue
      const p = ((yMin + y) * W + xMin + x) * 4
      const q = (y * rw + x) * 3
      d[p] = blurred[q]
      d[p + 1] = blurred[q + 1]
      d[p + 2] = blurred[q + 2]
    }
  }
}

export function applyOperations(image: ImageData, ops: SmudgeOperation[]): boolean {
  for (const op of ops) applySmudge(image, op)
  return ops.length > 0
}

/** cv2.GaussianBlur with kernel int(6*sigma+1) made odd and reflect-101 borders. */
export function gaussianBlurRegion(image: ImageData, x0: number, y0: number, rw: number, rh: number, sigma: number): Float32Array {
  let k = Math.trunc(6 * sigma + 1)
  if (k % 2 === 0) k += 1
  const half = Math.floor(k / 2)
  const kernel = new Float32Array(k)
  let sum = 0
  for (let i = 0; i < k; i++) {
    const v = Math.exp(-((i - half) * (i - half)) / (2 * sigma * sigma))
    kernel[i] = v
    sum += v
  }
  for (let i = 0; i < k; i++) kernel[i] /= sum

  const d = image.data
  const W = image.width
  const src = new Float32Array(rw * rh * 3)
  for (let y = 0; y < rh; y++) {
    for (let x = 0; x < rw; x++) {
      const p = ((y0 + y) * W + x0 + x) * 4
      const q = (y * rw + x) * 3
      src[q] = d[p]
      src[q + 1] = d[p + 1]
      src[q + 2] = d[p + 2]
    }
  }
  const reflect = (i: number, n: number) => {
    if (n === 1) return 0
    const period = 2 * (n - 1)
    let m = Math.abs(i) % period
    if (m >= n) m = period - m
    return m
  }
  const tmp = new Float32Array(rw * rh * 3)
  for (let y = 0; y < rh; y++) {
    for (let x = 0; x < rw; x++) {
      let r = 0
      let g = 0
      let b = 0
      for (let i = 0; i < k; i++) {
        const sx = reflect(x + i - half, rw)
        const q = (y * rw + sx) * 3
        r += src[q] * kernel[i]
        g += src[q + 1] * kernel[i]
        b += src[q + 2] * kernel[i]
      }
      const o = (y * rw + x) * 3
      tmp[o] = r
      tmp[o + 1] = g
      tmp[o + 2] = b
    }
  }
  const out = new Float32Array(rw * rh * 3)
  for (let y = 0; y < rh; y++) {
    for (let x = 0; x < rw; x++) {
      let r = 0
      let g = 0
      let b = 0
      for (let i = 0; i < k; i++) {
        const sy = reflect(y + i - half, rh)
        const q = (sy * rw + x) * 3
        r += tmp[q] * kernel[i]
        g += tmp[q + 1] * kernel[i]
        b += tmp[q + 2] * kernel[i]
      }
      const o = (y * rw + x) * 3
      out[o] = r
      out[o + 1] = g
      out[o + 2] = b
    }
  }
  return out
}

export function serializeOperations(ops: SmudgeOperation[], sourceName: string): string {
  return JSON.stringify({ version: 1, source: sourceName, operations: ops }, null, 2)
}

export function parseOperations(json: string): SmudgeOperation[] {
  const parsed = JSON.parse(json) as { operations?: SmudgeOperation[] }
  if (!Array.isArray(parsed.operations)) throw new Error('Not a Sightline smudge file')
  return parsed.operations
}
