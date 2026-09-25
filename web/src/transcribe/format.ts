import type { TranscriptResult } from './types'

/** Same layout as TranscriptionView._write_transcription_output on desktop. */
export function toText(result: TranscriptResult, sourceName: string): string {
  const lines = [`Transcription for: ${sourceName}`, `Language: ${result.language}`, '='.repeat(60), '']
  for (const s of result.segments) {
    if (!s.text) continue
    lines.push(`${s.start.toFixed(2)}–${s.end.toFixed(2)}  ${s.speaker ?? 'Unknown'}: ${s.text}`)
  }
  if (result.segments.length === 0) lines.push(result.text || 'No transcription available.')
  return lines.join('\n') + '\n'
}

export function toSrt(result: TranscriptResult): string {
  return result.segments
    .filter((s) => s.text)
    .map((s, i) => `${i + 1}\n${srtTime(s.start)} --> ${srtTime(s.end)}\n${s.speaker ? `[${s.speaker}] ` : ''}${s.text}\n`)
    .join('\n')
}

export function toJson(result: TranscriptResult): string {
  return JSON.stringify(result, null, 2)
}

function srtTime(seconds: number): string {
  const ms = Math.round(seconds * 1000)
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  const r = ms % 1000
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(r).padStart(3, '0')}`
}
