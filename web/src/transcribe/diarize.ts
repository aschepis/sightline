import type { Segment, SpeakerTurn, Word } from './types'

export interface RawTurn {
  start: number
  end: number
}

export function cosineDistance(a: Float32Array, b: Float32Array): number {
  let dot = 0
  let na = 0
  let nb = 0
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]
    na += a[i] * a[i]
    nb += b[i] * b[i]
  }
  if (na === 0 || nb === 0) return 1
  return 1 - dot / Math.sqrt(na * nb)
}

/**
 * Average-linkage agglomerative clustering on cosine distance. Stops at
 * `numClusters` when given, otherwise when the closest pair is farther than
 * `threshold`. Returns a cluster label per embedding.
 */
export function clusterEmbeddings(embeddings: Float32Array[], numClusters: number | null, threshold = 0.45): number[] {
  const n = embeddings.length
  if (n === 0) return []
  const dist: number[][] = embeddings.map((a) => embeddings.map((b) => cosineDistance(a, b)))
  let clusters: number[][] = embeddings.map((_, i) => [i])
  const target = numClusters ? Math.max(1, Math.min(numClusters, n)) : 1
  while (clusters.length > target) {
    let best = Infinity
    let bi = -1
    let bj = -1
    for (let i = 0; i < clusters.length; i++) {
      for (let j = i + 1; j < clusters.length; j++) {
        let sum = 0
        for (const a of clusters[i]) for (const b of clusters[j]) sum += dist[a][b]
        const avg = sum / (clusters[i].length * clusters[j].length)
        if (avg < best) {
          best = avg
          bi = i
          bj = j
        }
      }
    }
    if (!numClusters && best > threshold) break
    const merged = [...clusters[bi], ...clusters[bj]]
    clusters = clusters.filter((_, k) => k !== bi && k !== bj)
    clusters.push(merged)
  }
  // Label clusters in order of first appearance so SPEAKER_00 speaks first.
  const ordered = clusters.map((members) => ({ members, first: Math.min(...members) })).sort((a, b) => a.first - b.first)
  const labels = new Array<number>(n).fill(0)
  ordered.forEach((c, label) => c.members.forEach((m) => (labels[m] = label)))
  return labels
}

export function speakerName(index: number): string {
  return `SPEAKER_${String(index).padStart(2, '0')}`
}

/** Merge consecutive turns of the same speaker separated by a short gap. */
export function mergeTurns(turns: SpeakerTurn[], maxGap = 0.5): SpeakerTurn[] {
  const sorted = [...turns].sort((a, b) => a.start - b.start)
  const out: SpeakerTurn[] = []
  for (const t of sorted) {
    const last = out[out.length - 1]
    if (last && last.speaker === t.speaker && t.start - last.end <= maxGap) {
      last.end = Math.max(last.end, t.end)
    } else {
      out.push({ ...t })
    }
  }
  return out
}

function overlap(aStart: number, aEnd: number, bStart: number, bEnd: number): number {
  return Math.max(0, Math.min(aEnd, bEnd) - Math.max(aStart, bStart))
}

function bestSpeaker(start: number, end: number, turns: SpeakerTurn[]): string | undefined {
  let best: string | undefined
  let bestOverlap = 0
  let nearest: string | undefined
  let nearestDistance = Infinity
  for (const t of turns) {
    const o = overlap(start, end, t.start, t.end)
    if (o > bestOverlap) {
      bestOverlap = o
      best = t.speaker
    }
    const distance = start > t.end ? start - t.end : t.start > end ? t.start - end : 0
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearest = t.speaker
    }
  }
  return best ?? (nearestDistance <= 2 ? nearest : undefined)
}

/**
 * Port of whisperx.assign_word_speakers: each segment gets the speaker with
 * the most overlap, then each word does the same, falling back to the
 * segment's speaker.
 */
export function assignWordSpeakers(turns: SpeakerTurn[], segments: Segment[]): Segment[] {
  return segments.map((segment) => {
    const speaker = bestSpeaker(segment.start, segment.end, turns)
    const words: Word[] = segment.words.map((w) => ({ ...w, speaker: bestSpeaker(w.start, w.end, turns) ?? speaker }))
    return { ...segment, speaker, words }
  })
}

/**
 * Splits segments wherever the speaker changes mid-sentence so each output
 * line has one speaker, like the desktop transcript.
 */
export function splitSegmentsBySpeaker(segments: Segment[]): Segment[] {
  const out: Segment[] = []
  for (const segment of segments) {
    if (segment.words.length === 0) {
      out.push(segment)
      continue
    }
    let current: Word[] = []
    const flush = () => {
      if (current.length === 0) return
      out.push({
        start: current[0].start,
        end: current[current.length - 1].end,
        text: current.map((w) => w.text).join('').trim(),
        speaker: current[0].speaker ?? segment.speaker,
        words: current,
      })
      current = []
    }
    for (const word of segment.words) {
      if (current.length > 0 && word.speaker !== current[0].speaker) flush()
      current.push(word)
    }
    flush()
  }
  return out
}

export interface WordChunk {
  text: string
  timestamp: [number, number | null]
}

/**
 * Groups Whisper word chunks into sentence-like segments: break on sentence
 * punctuation, on pauses longer than a second, or every 40 words.
 */
export function wordsToSegments(chunks: WordChunk[], durationSeconds: number): Segment[] {
  const segments: Segment[] = []
  let current: Word[] = []
  const flush = () => {
    if (current.length === 0) return
    segments.push({
      start: current[0].start,
      end: current[current.length - 1].end,
      text: current.map((w) => w.text).join('').trim(),
      words: current,
    })
    current = []
  }
  for (let i = 0; i < chunks.length; i++) {
    const c = chunks[i]
    const start = c.timestamp[0] ?? (current.length ? current[current.length - 1].end : 0)
    const end = c.timestamp[1] ?? Math.min(durationSeconds, start + 0.5)
    const previous = current[current.length - 1]
    if (previous && start - previous.end > 1.0) flush()
    current.push({ text: c.text, start, end })
    if (/[.!?。！？]["')\]]?\s*$/.test(c.text) || current.length >= 40) flush()
  }
  flush()
  return segments
}
