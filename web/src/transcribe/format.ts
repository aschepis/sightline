import type { TranscriptResult } from './types'

export type SpeakerNames = Record<string, string>

/** Machine labels in order of first appearance. */
export function speakerLabels(result: TranscriptResult): string[] {
  const seen: string[] = []
  for (const s of [...result.turns, ...result.segments]) {
    if (s.speaker && !seen.includes(s.speaker)) seen.push(s.speaker)
  }
  return seen
}

export function displayName(label: string | undefined, names: SpeakerNames): string {
  if (!label) return 'Unknown'
  const custom = names[label]?.trim()
  return custom ? custom : label
}

/** Returns a copy with speakers replaced by the names the user typed. */
export function renameSpeakers(result: TranscriptResult, names: SpeakerNames): TranscriptResult {
  const map = (label?: string) => (label ? displayName(label, names) : label)
  return {
    ...result,
    turns: result.turns.map((t) => ({ ...t, speaker: displayName(t.speaker, names) })),
    segments: result.segments.map((seg) => ({ ...seg, speaker: map(seg.speaker), words: seg.words.map((w) => ({ ...w, speaker: map(w.speaker) })) })),
  }
}

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

/** JSON keeps both the machine label and the name so nothing is lost. */
export function toJson(result: TranscriptResult, names: SpeakerNames = {}): string {
  const { debug: _debug, ...rest } = result
  const withIds = {
    ...rest,
    speakerNames: names,
    turns: rest.turns.map((t) => ({ ...t, speakerId: t.speaker, speaker: displayName(t.speaker, names) })),
    segments: rest.segments.map((seg) => ({
      ...seg,
      speakerId: seg.speaker,
      speaker: seg.speaker ? displayName(seg.speaker, names) : undefined,
      words: seg.words.map((w) => ({ ...w, speakerId: w.speaker, speaker: w.speaker ? displayName(w.speaker, names) : undefined })),
    })),
  }
  return JSON.stringify(withIds, null, 2)
}

function srtTime(seconds: number): string {
  const ms = Math.round(seconds * 1000)
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  const r = ms % 1000
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(r).padStart(3, '0')}`
}
