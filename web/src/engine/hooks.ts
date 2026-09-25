import { useEffect, useState } from 'react'
import { engine } from './index'
import type { Job } from './types'
import type { AppConfig } from '../lib/config'
import type { Capabilities } from '../lib/capabilities'

export function useJobs(): Job[] {
  const [jobs, setJobs] = useState<Job[]>(engine.queue.snapshot())
  useEffect(() => engine.queue.subscribe(setJobs), [])
  return jobs
}

export function useConfig(): [AppConfig, (patch: Partial<AppConfig> | ((c: AppConfig) => AppConfig)) => void] {
  const [config, setConfig] = useState<AppConfig>(engine.config)
  useEffect(() => engine.subscribeConfig(setConfig), [])
  return [config, (patch) => engine.updateConfig(patch)]
}

export function useCapabilities(): Capabilities | null {
  const [caps, setCaps] = useState<Capabilities | null>(engine.capabilities)
  useEffect(() => {
    void engine.ready.then(() => setCaps(engine.capabilities))
  }, [])
  return caps
}
