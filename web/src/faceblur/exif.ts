/**
 * Copies the EXIF APP1 segment from a source JPEG into a freshly encoded
 * JPEG, which is what deface's --keep-metadata does for images.
 */
export function copyJpegExif(source: Uint8Array, target: Uint8Array): Uint8Array {
  const exif = findApp1Exif(source)
  if (!exif) return target
  if (target.length < 2 || target[0] !== 0xff || target[1] !== 0xd8) return target
  const out = new Uint8Array(target.length + exif.length)
  out.set(target.subarray(0, 2), 0)
  out.set(exif, 2)
  out.set(target.subarray(2), 2 + exif.length)
  return out
}

function findApp1Exif(bytes: Uint8Array): Uint8Array | null {
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return null
  let offset = 2
  while (offset + 4 <= bytes.length) {
    if (bytes[offset] !== 0xff) return null
    const marker = bytes[offset + 1]
    if (marker === 0xda || marker === 0xd9) return null
    const length = (bytes[offset + 2] << 8) | bytes[offset + 3]
    if (marker === 0xe1 && bytes.length >= offset + 10) {
      const tag = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8))
      if (tag === 'Exif') return bytes.slice(offset, offset + 2 + length)
    }
    offset += 2 + length
  }
  return null
}
