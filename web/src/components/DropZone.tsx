import { useRef, useState, type DragEvent } from 'react'

interface Props {
  accept: string
  multiple?: boolean
  label: string
  hint?: string
  onFiles: (files: File[]) => void
}

export function DropZone({ accept, multiple = true, label, hint, onFiles }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [active, setActive] = useState(false)
  const handle = (list: FileList | null) => {
    if (!list) return
    const files = Array.from(list)
    onFiles(multiple ? files : files.slice(0, 1))
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setActive(false)
    handle(e.dataTransfer.files)
  }
  return (
    <div
      className={`dropzone ${active ? 'active' : ''}`}
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        setActive(true)
      }}
      onDragLeave={() => setActive(false)}
      onDrop={onDrop}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
    >
      <strong>{label}</strong>
      {hint && (
        <>
          <br />
          <span className="small">{hint}</span>
        </>
      )}
      <input ref={input} type="file" accept={accept} multiple={multiple} hidden onChange={(e) => handle(e.target.files)} />
    </div>
  )
}
