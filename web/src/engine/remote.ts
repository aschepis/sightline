import type { Executor, JobOutput, JobProgress, JobRequest } from './types'

/**
 * Sends a job to the optional server-side executor described in
 * WEB_APP_PLAN.md section 5.2. The API contract is small on purpose:
 *   POST {endpoint}/jobs            -> { id, uploadUrl }
 *   PUT  uploadUrl                   (the media file)
 *   POST {endpoint}/jobs/{id}/start  -> 202
 *   GET  {endpoint}/jobs/{id}        -> { status, progress, message, downloadUrl?, error? }
 * Media leaves the device only when the user picks this executor explicitly.
 */
export class RemoteExecutor implements Executor {
  readonly name = 'remote'

  private endpoint: string

  constructor(endpoint: string) {
    this.endpoint = endpoint
  }

  supports(): boolean {
    return this.endpoint.trim().length > 0
  }

  async run(
    request: JobRequest,
    signal: AbortSignal,
    onProgress: (p: JobProgress) => void,
    onLog: (line: string) => void,
  ): Promise<JobOutput> {
    const base = this.endpoint.replace(/\/$/, '')
    const body = serialize(request)
    onLog(`Creating remote job at ${base}`)
    const created = await json<{ id: string; uploadUrl: string }>(await fetch(`${base}/jobs`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal }))
    onProgress({ fraction: 0.02, message: 'Uploading' })
    await fetch(created.uploadUrl, { method: 'PUT', body: request.file, signal })
    await fetch(`${base}/jobs/${created.id}/start`, { method: 'POST', signal })

    for (;;) {
      if (signal.aborted) throw new Error('Cancelled')
      const status = await json<{ status: string; progress: number; message?: string; downloadUrl?: string; error?: string; result?: unknown }>(
        await fetch(`${base}/jobs/${created.id}`, { signal }),
      )
      onProgress({ fraction: 0.05 + 0.9 * (status.progress ?? 0), message: status.message })
      if (status.status === 'failed') throw new Error(status.error ?? 'Remote job failed')
      if (status.status === 'success') {
        if (request.kind === 'transcribe') {
          return { kind: 'transcribe', result: status.result as JobOutput extends { kind: 'transcribe'; result: infer R } ? R : never, filename: request.file.name }
        }
        const blob = await (await fetch(status.downloadUrl!, { signal })).blob()
        if (request.kind === 'face-blur') return { kind: 'face-blur', blob, filename: request.file.name, facesDetected: 0 }
        return { kind: 'smudge-export', blob, filename: request.file.name }
      }
      await new Promise((r) => setTimeout(r, 2000))
    }
  }
}

function serialize(request: JobRequest): Record<string, unknown> {
  switch (request.kind) {
    case 'face-blur':
      return { kind: request.kind, filename: request.file.name, options: request.options }
    case 'smudge-export':
      return { kind: request.kind, filename: request.file.name, operations: request.operations }
    case 'transcribe':
      return { kind: request.kind, filename: request.file.name, options: request.options }
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`Remote executor returned ${response.status}`)
  return (await response.json()) as T
}
