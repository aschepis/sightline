export type Rotation = 0 | 90 | 180 | 270

/**
 * Track header matrices are 16.16 fixed point [a b u c d v x y w]. Phones
 * record landscape frames and store the display rotation here, which
 * ffmpeg applies on decode and WebCodecs does not.
 */
export function rotationFromMatrix(matrix: ArrayLike<number> | undefined): Rotation {
  if (!matrix || matrix.length < 5) return 0
  const a = matrix[0] / 65536
  const b = matrix[1] / 65536
  const degrees = Math.round((Math.atan2(b, a) * 180) / Math.PI)
  const normalized = ((degrees % 360) + 360) % 360
  if (normalized === 90 || normalized === 180 || normalized === 270) return normalized
  return 0
}

export function displaySize(width: number, height: number, rotation: Rotation): { width: number; height: number } {
  return rotation === 90 || rotation === 270 ? { width: height, height: width } : { width, height }
}

/** Draws a frame upright onto a canvas already sized with displaySize(). */
export function drawUpright(ctx: OffscreenCanvasRenderingContext2D | CanvasRenderingContext2D, source: CanvasImageSource, rotation: Rotation, srcWidth: number, srcHeight: number): void {
  const { width: outW, height: outH } = displaySize(srcWidth, srcHeight, rotation)
  if (rotation === 0) {
    ctx.drawImage(source, 0, 0, srcWidth, srcHeight)
    return
  }
  ctx.save()
  if (rotation === 90) {
    ctx.translate(outW, 0)
    ctx.rotate(Math.PI / 2)
  } else if (rotation === 180) {
    ctx.translate(outW, outH)
    ctx.rotate(Math.PI)
  } else {
    ctx.translate(0, outH)
    ctx.rotate(-Math.PI / 2)
  }
  ctx.drawImage(source, 0, 0, srcWidth, srcHeight)
  ctx.restore()
}
