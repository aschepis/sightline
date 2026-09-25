export interface Capabilities {
  webgpu: boolean
  webcodecs: boolean
  sharedArrayBuffer: boolean
  crossOriginIsolated: boolean
  hardwareConcurrency: number
  /** Approximate device memory in GB when the browser reports it. */
  deviceMemoryGb: number | null
  fileSystemAccess: boolean
}

let cached: Promise<Capabilities> | null = null

export function probeCapabilities(): Promise<Capabilities> {
  if (!cached) cached = probe()
  return cached
}

async function probe(): Promise<Capabilities> {
  let webgpu = false
  try {
    const gpu = (navigator as Navigator & { gpu?: GPU }).gpu
    if (gpu) {
      const adapter = await gpu.requestAdapter()
      webgpu = adapter !== null
    }
  } catch {
    webgpu = false
  }
  const nav = navigator as Navigator & { deviceMemory?: number }
  return {
    webgpu,
    webcodecs: typeof VideoDecoder !== 'undefined' && typeof VideoEncoder !== 'undefined',
    sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
    crossOriginIsolated: globalThis.crossOriginIsolated === true,
    hardwareConcurrency: navigator.hardwareConcurrency || 2,
    deviceMemoryGb: nav.deviceMemory ?? null,
    fileSystemAccess: 'showSaveFilePicker' in globalThis,
  }
}
