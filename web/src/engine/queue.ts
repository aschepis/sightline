import type { Executor, Job, JobOutput, JobRequest } from './types'

type Listener = (jobs: Job[]) => void

/**
 * Runs jobs with a concurrency limit, like the desktop batch view. Jobs are
 * immutable snapshots handed to listeners so React can render them directly.
 */
export class JobQueue {
  private jobs: Job[] = []
  private controllers = new Map<string, AbortController>()
  private listeners = new Set<Listener>()
  private running = 0

  private executor: Executor
  concurrency: number

  constructor(executor: Executor, concurrency: number) {
    this.executor = executor
    this.concurrency = concurrency
  }

  setExecutor(executor: Executor): void {
    this.executor = executor
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    listener(this.jobs)
    return () => this.listeners.delete(listener)
  }

  snapshot(): Job[] {
    return this.jobs
  }

  add(request: JobRequest): Job {
    const job: Job = { id: crypto.randomUUID(), request, status: 'pending', progress: { fraction: 0 }, log: [] }
    this.jobs = [...this.jobs, job]
    this.emit()
    return job
  }

  remove(id: string): void {
    this.cancel(id)
    this.jobs = this.jobs.filter((j) => j.id !== id)
    this.emit()
  }

  clearFinished(): void {
    this.jobs = this.jobs.filter((j) => j.status === 'pending' || j.status === 'processing')
    this.emit()
  }

  cancel(id: string): void {
    this.controllers.get(id)?.abort()
    const job = this.jobs.find((j) => j.id === id)
    if (job && job.status === 'pending') this.update(id, { status: 'cancelled' })
  }

  cancelAll(): void {
    for (const job of this.jobs) this.cancel(job.id)
  }

  start(): void {
    this.pump()
  }

  private pump(): void {
    while (this.running < this.concurrency) {
      const next = this.jobs.find((j) => j.status === 'pending')
      if (!next) return
      this.running += 1
      void this.runJob(next.id).finally(() => {
        this.running -= 1
        this.pump()
      })
    }
  }

  private async runJob(id: string): Promise<void> {
    const job = this.jobs.find((j) => j.id === id)
    if (!job || job.status !== 'pending') return
    const controller = new AbortController()
    this.controllers.set(id, controller)
    this.update(id, { status: 'processing', startedAt: Date.now(), progress: { fraction: 0 }, error: undefined })
    try {
      const output: JobOutput = await this.executor.run(
        job.request,
        controller.signal,
        (progress) => this.update(id, { progress }),
        (line) => this.appendLog(id, line),
      )
      this.update(id, { status: 'success', output, progress: { fraction: 1 }, finishedAt: Date.now() })
    } catch (err) {
      const cancelled = controller.signal.aborted
      const message = err instanceof Error ? err.message : String(err)
      this.appendLog(id, message)
      this.update(id, { status: cancelled ? 'cancelled' : 'failed', error: cancelled ? undefined : message, finishedAt: Date.now() })
    } finally {
      this.controllers.delete(id)
    }
  }

  private appendLog(id: string, line: string): void {
    const job = this.jobs.find((j) => j.id === id)
    if (!job) return
    this.update(id, { log: [...job.log.slice(-199), line] })
  }

  private update(id: string, patch: Partial<Job>): void {
    this.jobs = this.jobs.map((j) => (j.id === id ? { ...j, ...patch } : j))
    this.emit()
  }

  private emit(): void {
    for (const listener of this.listeners) listener(this.jobs)
  }
}
