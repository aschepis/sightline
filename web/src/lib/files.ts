export function outputFilename(inputName: string, suffix: string, newExtension?: string): string {
  const dot = inputName.lastIndexOf('.')
  const base = dot > 0 ? inputName.slice(0, dot) : inputName
  const ext = newExtension ?? (dot > 0 ? inputName.slice(dot) : '')
  return `${base}${suffix}${ext}`
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export function isImageFile(file: File): boolean {
  return file.type.startsWith('image/') || /\.(jpe?g|png|bmp|tiff?|webp)$/i.test(file.name)
}

export function isVideoFile(file: File): boolean {
  return file.type.startsWith('video/') || /\.(mp4|mov|m4v|mkv|webm|avi)$/i.test(file.name)
}

export function isAudioFile(file: File): boolean {
  return file.type.startsWith('audio/') || /\.(mp3|wav|m4a|aac|flac|ogg|opus)$/i.test(file.name)
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`
}
