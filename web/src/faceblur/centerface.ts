// Port of deface/centerface.py. Same input layout (RGB, 0..255, NCHW), same
// decode and NMS so detections match the desktop app.

export interface Detection {
  x1: number
  y1: number
  x2: number
  y2: number
  score: number
}

export interface CenterFaceOutputs {
  heatmap: Float32Array
  scale: Float32Array
  offset: Float32Array
  /** Feature map height and width. */
  fh: number
  fw: number
}

export function shapeTransform(inWidth: number, inHeight: number, origWidth: number, origHeight: number) {
  const wNew = Math.ceil(inWidth / 32) * 32
  const hNew = Math.ceil(inHeight / 32) * 32
  return { wNew, hNew, scaleW: wNew / origWidth, scaleH: hNew / origHeight }
}

/** RGBA pixels -> planar RGB float tensor, values kept in 0..255 like deface. */
export function rgbaToTensor(rgba: Uint8ClampedArray, width: number, height: number): Float32Array {
  const plane = width * height
  const out = new Float32Array(plane * 3)
  for (let i = 0, p = 0; i < plane; i++, p += 4) {
    out[i] = rgba[p]
    out[plane + i] = rgba[p + 1]
    out[2 * plane + i] = rgba[p + 2]
  }
  return out
}

export function decodeDetections(out: CenterFaceOutputs, sizeH: number, sizeW: number, threshold: number): Detection[] {
  const { heatmap, scale, offset, fh, fw } = out
  const plane = fh * fw
  const boxes: Detection[] = []
  for (let c0 = 0; c0 < fh; c0++) {
    for (let c1 = 0; c1 < fw; c1++) {
      const idx = c0 * fw + c1
      const s = heatmap[idx]
      if (s <= threshold) continue
      const s0 = Math.exp(scale[idx]) * 4
      const s1 = Math.exp(scale[plane + idx]) * 4
      const o0 = offset[idx]
      const o1 = offset[plane + idx]
      let x1 = Math.max(0, (c1 + o1 + 0.5) * 4 - s1 / 2)
      let y1 = Math.max(0, (c0 + o0 + 0.5) * 4 - s0 / 2)
      x1 = Math.min(x1, sizeW)
      y1 = Math.min(y1, sizeH)
      boxes.push({ x1, y1, x2: Math.min(x1 + s1, sizeW), y2: Math.min(y1 + s0, sizeH), score: s })
    }
  }
  return nms(boxes, 0.3)
}

export function nms(boxes: Detection[], threshold: number): Detection[] {
  const order = boxes.map((_, i) => i).sort((a, b) => boxes[b].score - boxes[a].score)
  const suppressed = new Uint8Array(boxes.length)
  const keep: Detection[] = []
  const area = (b: Detection) => (b.x2 - b.x1) * (b.y2 - b.y1)
  for (let oi = 0; oi < order.length; oi++) {
    const i = order[oi]
    if (suppressed[i]) continue
    keep.push(boxes[i])
    const bi = boxes[i]
    const ai = area(bi)
    for (let oj = oi + 1; oj < order.length; oj++) {
      const j = order[oj]
      if (suppressed[j]) continue
      const bj = boxes[j]
      const w = Math.max(0, Math.min(bi.x2, bj.x2) - Math.max(bi.x1, bj.x1))
      const h = Math.max(0, Math.min(bi.y2, bj.y2) - Math.max(bi.y1, bj.y1))
      const inter = w * h
      const ovr = inter / (ai + area(bj) - inter)
      if (ovr >= threshold) suppressed[j] = 1
    }
  }
  return keep
}

/** Map detections from detector input space back to the original frame. */
export function rescaleDetections(dets: Detection[], scaleW: number, scaleH: number): Detection[] {
  return dets.map((d) => ({ x1: d.x1 / scaleW, y1: d.y1 / scaleH, x2: d.x2 / scaleW, y2: d.y2 / scaleH, score: d.score }))
}
