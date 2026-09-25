import { useState } from 'react'
import { engine } from '../engine'
import type { Job } from '../engine/types'
import { downloadBlob } from '../lib/files'

const LABELS: Record<Job['status'], string> = { pending: 'Pending', processing: 'Processing', success: 'Success', failed: 'Failed', cancelled: 'Cancelled' }

export function JobTable({ jobs, onOpen }: { jobs: Job[]; onOpen?: (job: Job) => void }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  if (jobs.length === 0) return <p className="muted">No files queued.</p>
  return (
    <table className="jobs">
      <thead>
        <tr>
          <th>File</th>
          <th>Status</th>
          <th>Progress</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} expanded={expanded === job.id} toggle={() => setExpanded(expanded === job.id ? null : job.id)} onOpen={onOpen} />
        ))}
      </tbody>
    </table>
  )
}

function JobRow({ job, expanded, toggle, onOpen }: { job: Job; expanded: boolean; toggle: () => void; onOpen?: (job: Job) => void }) {
  const out = job.output
  const seconds = job.startedAt && job.finishedAt ? ((job.finishedAt - job.startedAt) / 1000).toFixed(1) : null
  return (
    <>
      <tr>
        <td>
          <div>{job.request.file.name}</div>
          <div className="small muted">
            {job.progress.message ?? ''}
            {seconds ? ` · ${seconds}s` : ''}
            {out?.kind === 'face-blur' ? ` · ${out.facesDetected} face detection(s)` : ''}
          </div>
        </td>
        <td>
          <span className={`badge ${job.status}`}>{LABELS[job.status]}</span>
        </td>
        <td>
          <div className="progress">
            <div style={{ width: `${Math.round(job.progress.fraction * 100)}%` }} />
          </div>
        </td>
        <td className="row" style={{ justifyContent: 'flex-end' }}>
          {job.status === 'success' && out && 'blob' in out && (
            <button className="icon" onClick={() => downloadBlob(out.blob, out.filename)}>
              Save
            </button>
          )}
          {job.status === 'success' && out && onOpen && (
            <button className="icon secondary" onClick={() => onOpen(job)}>
              View
            </button>
          )}
          {(job.status === 'processing' || job.status === 'pending') && (
            <button className="icon secondary" onClick={() => engine.queue.cancel(job.id)}>
              Cancel
            </button>
          )}
          {job.status !== 'processing' && (
            <button className="icon secondary" onClick={() => engine.queue.remove(job.id)}>
              Remove
            </button>
          )}
          <button className="icon secondary" onClick={toggle}>
            {expanded ? 'Hide log' : 'Log'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4}>
            <div className="log">{[...job.log, job.error ? `Error: ${job.error}` : ''].filter(Boolean).join('\n') || 'No output yet.'}</div>
          </td>
        </tr>
      )}
    </>
  )
}
