import { describe, expect, it } from 'vitest'
import { assignWordSpeakers, clusterEmbeddings, mergeTurns, splitSegmentsBySpeaker, wordsToSegments } from '../src/transcribe/diarize'
import { toSrt, toText } from '../src/transcribe/format'

describe('clusterEmbeddings', () => {
  it('groups similar vectors and labels by first appearance', () => {
    const a = new Float32Array([1, 0, 0])
    const b = new Float32Array([0, 1, 0])
    const labels = clusterEmbeddings([a, b, new Float32Array([0.9, 0.1, 0]), new Float32Array([0.1, 0.95, 0])], null, 0.3)
    expect(labels).toEqual([0, 1, 0, 1])
  })

  it('honours a requested speaker count', () => {
    const vectors = [new Float32Array([1, 0]), new Float32Array([0.99, 0.01]), new Float32Array([0, 1])]
    expect(new Set(clusterEmbeddings(vectors, 1)).size).toBe(1)
    expect(new Set(clusterEmbeddings(vectors, 2)).size).toBe(2)
  })
})

describe('mergeTurns', () => {
  it('joins adjacent turns from the same speaker', () => {
    const merged = mergeTurns([
      { start: 0, end: 1, speaker: 'SPEAKER_00' },
      { start: 1.2, end: 2, speaker: 'SPEAKER_00' },
      { start: 2.1, end: 3, speaker: 'SPEAKER_01' },
    ])
    expect(merged).toEqual([
      { start: 0, end: 2, speaker: 'SPEAKER_00' },
      { start: 2.1, end: 3, speaker: 'SPEAKER_01' },
    ])
  })
})

describe('word to segment pipeline', () => {
  const chunks = [
    { text: ' Hello', timestamp: [0, 0.4] as [number, number] },
    { text: ' there.', timestamp: [0.4, 0.8] as [number, number] },
    { text: ' Fine', timestamp: [1.0, 1.3] as [number, number] },
    { text: ' thanks.', timestamp: [1.3, 1.7] as [number, number] },
  ]
  const turns = [
    { start: 0, end: 0.9, speaker: 'SPEAKER_00' },
    { start: 0.9, end: 2, speaker: 'SPEAKER_01' },
  ]

  it('splits on sentence punctuation', () => {
    const segments = wordsToSegments(chunks, 2)
    expect(segments.map((s) => s.text)).toEqual(['Hello there.', 'Fine thanks.'])
  })

  it('assigns speakers per word and per segment', () => {
    const segments = splitSegmentsBySpeaker(assignWordSpeakers(turns, wordsToSegments(chunks, 2)))
    expect(segments.map((s) => s.speaker)).toEqual(['SPEAKER_00', 'SPEAKER_01'])
  })

  it('formats like the desktop app', () => {
    const segments = splitSegmentsBySpeaker(assignWordSpeakers(turns, wordsToSegments(chunks, 2)))
    const text = toText({ language: 'en', segments, turns, text: '', durationSeconds: 2, model: 'x' }, 'a.wav')
    expect(text).toContain('Transcription for: a.wav')
    expect(text).toContain('0.00–0.80  SPEAKER_00: Hello there.')
    const srt = toSrt({ language: 'en', segments, turns, text: '', durationSeconds: 2, model: 'x' })
    expect(srt).toContain('00:00:00,000 --> 00:00:00,800')
  })
})

describe('speaker names', () => {
  it('applies typed names to text, srt and json output', async () => {
    const { renameSpeakers, toJson, speakerLabels } = await import('../src/transcribe/format')
    const result = {
      language: 'en',
      text: '',
      durationSeconds: 2,
      model: 'x',
      turns: [{ start: 0, end: 1, speaker: 'SPEAKER_00' }],
      segments: [{ start: 0, end: 1, text: 'Hi.', speaker: 'SPEAKER_00', words: [{ text: 'Hi.', start: 0, end: 1, speaker: 'SPEAKER_00' }] }],
    }
    expect(speakerLabels(result)).toEqual(['SPEAKER_00'])
    const named = renameSpeakers(result, { SPEAKER_00: 'Maria' })
    expect(toText(named, 'a.wav')).toContain('Maria: Hi.')
    expect(toSrt(named)).toContain('[Maria] Hi.')
    const json = JSON.parse(toJson(result, { SPEAKER_00: 'Maria' }))
    expect(json.segments[0].speaker).toBe('Maria')
    expect(json.segments[0].speakerId).toBe('SPEAKER_00')
    expect(json.speakerNames).toEqual({ SPEAKER_00: 'Maria' })
    // Blank names fall back to the machine label.
    expect(toText(renameSpeakers(result, { SPEAKER_00: '  ' }), 'a.wav')).toContain('SPEAKER_00: Hi.')
  })
})
