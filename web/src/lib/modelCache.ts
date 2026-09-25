// Model files live in Cache Storage so the PWA works offline after the first
// download. transformers.js uses its own cache named "transformers-cache".
export const APP_MODEL_CACHE = 'sightline-models-v1'
export const TRANSFORMERS_CACHE = 'transformers-cache'

export interface CachedModelEntry {
  cache: string
  url: string
  bytes: number
}

export async function cachedFetch(url: string, onProgress?: (loaded: number, total: number) => void): Promise<ArrayBuffer> {
  const cache = await openCache(APP_MODEL_CACHE)
  const hit = cache ? await cache.match(url) : undefined
  if (hit) return hit.arrayBuffer()

  const response = await fetch(url)
  if (!response.ok) throw new Error(`Failed to download ${url}: ${response.status}`)
  const total = Number(response.headers.get('content-length') ?? 0)
  const chunks: Uint8Array[] = []
  let loaded = 0
  const reader = response.body?.getReader()
  if (reader) {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value)
      loaded += value.byteLength
      onProgress?.(loaded, total)
    }
  }
  const buffer = concat(chunks)
  if (cache) {
    await cache.put(url, new Response(buffer.slice(0), { headers: { 'content-length': String(buffer.byteLength) } }))
  }
  return buffer
}

export async function listCachedModels(): Promise<CachedModelEntry[]> {
  if (!('caches' in globalThis)) return []
  const entries: CachedModelEntry[] = []
  for (const name of [APP_MODEL_CACHE, TRANSFORMERS_CACHE]) {
    const cache = await openCache(name)
    if (!cache) continue
    for (const request of await cache.keys()) {
      const response = await cache.match(request)
      const bytes = response ? Number(response.headers.get('content-length') ?? 0) || (await response.clone().arrayBuffer()).byteLength : 0
      entries.push({ cache: name, url: request.url, bytes })
    }
  }
  return entries
}

export async function deleteCachedModel(entry: CachedModelEntry): Promise<void> {
  const cache = await openCache(entry.cache)
  if (cache) await cache.delete(entry.url)
}

export async function clearAllModels(): Promise<void> {
  if (!('caches' in globalThis)) return
  await Promise.all([caches.delete(APP_MODEL_CACHE), caches.delete(TRANSFORMERS_CACHE)])
}

async function openCache(name: string): Promise<Cache | null> {
  try {
    if (!('caches' in globalThis)) return null
    return await caches.open(name)
  } catch {
    return null
  }
}

function concat(chunks: Uint8Array[]): ArrayBuffer {
  const total = chunks.reduce((n, c) => n + c.byteLength, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const c of chunks) {
    out.set(c, offset)
    offset += c.byteLength
  }
  return out.buffer
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
