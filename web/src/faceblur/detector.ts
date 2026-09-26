import * as ort from 'onnxruntime-web/webgpu'
import { cachedFetch } from '../lib/modelCache'
import { ORT_WASM_PATHS } from '../lib/ortPaths'
import { decodeDetections, rescaleDetections, rgbaToTensor, shapeTransform, type Detection } from './centerface'
import { detectorInputSize } from './options'

export type DetectorBackend = 'webgpu' | 'wasm'

export const MODEL_URL = new URL('models/centerface.onnx', globalThis.location?.origin ? `${globalThis.location.origin}${import.meta.env.BASE_URL}` : 'http://localhost/').href
const INPUT_NAME = 'input.1'
const OUTPUT_NAMES = ['537', '538', '539', '540']

/**
 * CenterFace face detector running on ONNX Runtime Web. One instance per
 * worker; the session is created lazily on first detect().
 */
export class FaceDetector {
  private session: ort.InferenceSession | null = null
  private canvas: OffscreenCanvas | null = null
  readonly backend: DetectorBackend

  constructor(backend: DetectorBackend) {
    this.backend = backend
  }

  async load(onProgress?: (loaded: number, total: number) => void): Promise<DetectorBackend> {
    if (this.session) return this.backend
    ort.env.wasm.wasmPaths = ORT_WASM_PATHS
    ort.env.logLevel = 'error'
    ort.env.wasm.numThreads = globalThis.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 1) : 1
    const model = await cachedFetch(MODEL_URL, onProgress)
    const providers: ort.InferenceSession.ExecutionProviderConfig[] = this.backend === 'webgpu' ? ['webgpu', 'wasm'] : ['wasm']
    this.session = await ort.InferenceSession.create(model, { executionProviders: providers, graphOptimizationLevel: 'all', logSeverityLevel: 3 })
    return this.backend
  }

  /**
   * Detect faces on a frame. `scale` follows FaceBlurOptions.scale. Returns
   * boxes in the source frame's pixel space.
   */
  async detect(source: ImageBitmap | OffscreenCanvas | VideoFrame, srcWidth: number, srcHeight: number, scale: string, threshold: number): Promise<Detection[]> {
    if (!this.session) await this.load()
    const target = detectorInputSize(scale, srcWidth, srcHeight)
    const { wNew, hNew, scaleW, scaleH } = shapeTransform(target.width, target.height, srcWidth, srcHeight)
    if (!this.canvas || this.canvas.width !== wNew || this.canvas.height !== hNew) {
      this.canvas = new OffscreenCanvas(wNew, hNew)
    }
    const ctx = this.canvas.getContext('2d', { willReadFrequently: true })!
    ctx.drawImage(source, 0, 0, wNew, hNew)
    const rgba = ctx.getImageData(0, 0, wNew, hNew).data
    const tensor = new ort.Tensor('float32', rgbaToTensor(rgba, wNew, hNew), [1, 3, hNew, wNew])
    const results = await this.session!.run({ [INPUT_NAME]: tensor })
    const heatmap = results[OUTPUT_NAMES[0]]
    const fh = Number(heatmap.dims[2])
    const fw = Number(heatmap.dims[3])
    const dets = decodeDetections(
      {
        heatmap: heatmap.data as Float32Array,
        scale: results[OUTPUT_NAMES[1]].data as Float32Array,
        offset: results[OUTPUT_NAMES[2]].data as Float32Array,
        fh,
        fw,
      },
      hNew,
      wNew,
      threshold,
    )
    return rescaleDetections(dets, scaleW, scaleH)
  }

  async dispose(): Promise<void> {
    await this.session?.release()
    this.session = null
  }
}

/** Fetches the detector model into the browser cache without running it. */
export async function preloadFaceDetector(onProgress?: (loaded: number, total: number) => void): Promise<void> {
  await cachedFetch(MODEL_URL, onProgress)
}
