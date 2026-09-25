// Vite emits these as hashed assets, so the ORT runtime is served from this
// origin (works offline) instead of ORT's default CDN.
import mjs from 'onnxruntime-web/ort-wasm-simd-threaded.asyncify.mjs?url'
import wasm from 'onnxruntime-web/ort-wasm-simd-threaded.asyncify.wasm?url'

export const ORT_WASM_PATHS = { mjs, wasm }
