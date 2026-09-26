import { probeCapabilities, type Capabilities } from '../lib/capabilities'
import { loadConfig, saveConfig, type AppConfig } from '../lib/config'
import { LocalExecutor, chooseBackend } from './local'
import { JobQueue } from './queue'
import type { Executor } from './types'

type ConfigListener = (config: AppConfig) => void

/**
 * One engine per page: holds config, capabilities, executors and the queue.
 * Pages subscribe to config and jobs through React hooks in ./hooks.ts.
 */
class Engine {
  config: AppConfig = loadConfig()
  capabilities: Capabilities | null = null
  readonly queue: JobQueue
  private local = new LocalExecutor('wasm')
  private configListeners = new Set<ConfigListener>()
  readonly ready: Promise<void>

  constructor() {
    this.queue = new JobQueue(this.local, this.config.batchSize)
    this.ready = probeCapabilities().then((caps) => {
      this.capabilities = caps
      this.applyExecutor()
    })
  }

  updateConfig(patch: Partial<AppConfig> | ((c: AppConfig) => AppConfig)): void {
    this.config = typeof patch === 'function' ? patch(this.config) : { ...this.config, ...patch }
    saveConfig(this.config)
    this.queue.concurrency = this.config.batchSize
    this.applyExecutor()
    for (const l of this.configListeners) l(this.config)
  }

  subscribeConfig(listener: ConfigListener): () => void {
    this.configListeners.add(listener)
    return () => this.configListeners.delete(listener)
  }

  activeExecutor(): Executor {
    return this.queue['executor' as keyof JobQueue] as unknown as Executor
  }

  activeBackend(): 'webgpu' | 'wasm' {
    if (!this.capabilities) return 'wasm'
    return chooseBackend(this.config.execution, this.capabilities)
  }

  private applyExecutor(): void {
    if (!this.capabilities) return
    this.local.setBackend(chooseBackend(this.config.execution, this.capabilities))
    this.queue.setExecutor(this.local)
  }
}

export const engine = new Engine()

if (import.meta.env.DEV) {
  ;(globalThis as { __sightline?: Engine }).__sightline = engine
}
