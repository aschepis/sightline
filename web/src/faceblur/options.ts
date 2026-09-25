export type ReplaceMode = 'blur' | 'solid' | 'mosaic' | 'none'

/** Mirrors the deface CLI flags built by build_deface_args() in main.py. */
export interface FaceBlurOptions {
  /** Detection threshold. deface default 0.2 in Sightline. */
  thresh: number
  /**
   * Detector input size as "WxH", "auto" (longest side 640, keeps aspect) or
   * "full" (native size, slowest, deface's default).
   */
  scale: string
  /** Rectangular masks instead of ellipses. */
  boxes: boolean
  maskScale: number
  replacewith: ReplaceMode
  mosaicSize: number
  keepAudio: boolean
  keepMetadata: boolean
}

export const DEFAULT_FACE_BLUR_OPTIONS: FaceBlurOptions = {
  thresh: 0.2,
  scale: 'auto',
  boxes: false,
  maskScale: 1.3,
  replacewith: 'blur',
  mosaicSize: 20,
  keepAudio: true,
  keepMetadata: true,
}

/** Resolve the "scale" option to a detector input size for a given frame. */
export function detectorInputSize(scale: string, width: number, height: number): { width: number; height: number } {
  if (scale === 'full') return { width, height }
  const match = /^(\d+)x(\d+)$/i.exec(scale.trim())
  if (match) return { width: Number(match[1]), height: Number(match[2]) }
  const longest = Math.max(width, height)
  if (longest <= 640) return { width, height }
  const factor = 640 / longest
  return { width: Math.round(width * factor), height: Math.round(height * factor) }
}
