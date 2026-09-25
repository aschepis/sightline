/**
 * Copies the EXIF APP1 segment from a source JPEG into a freshly encoded
 * JPEG, which is what deface's --keep-metadata does for images. The browser
 * decodes images upright, so the Orientation tag is reset to 1 or viewers
 * would rotate the result a second time.
 */
export function copyJpegExif(source: Uint8Array, target: Uint8Array): Uint8Array {
  const found = findApp1Exif(source)
  if (!found) return target
  const exif = resetOrientation(found)
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

const ORIENTATION_TAG = 0x0112

export function resetOrientation(segment: Uint8Array): Uint8Array {
  const exif = segment.slice()
  const tiff = 10 // FF E1 len(2) "Exif\0\0"
  if (exif.length < tiff + 8) return exif
  const little = exif[tiff] === 0x49 && exif[tiff + 1] === 0x49
  const view = new DataView(exif.buffer, exif.byteOffset, exif.byteLength)
  const ifd0 = tiff + view.getUint32(tiff + 4, little)
  if (ifd0 + 2 > exif.length) return exif
  const count = view.getUint16(ifd0, little)
  for (let i = 0; i < count; i++) {
    const entry = ifd0 + 2 + i * 12
    if (entry + 12 > exif.length) break
    if (view.getUint16(entry, little) === ORIENTATION_TAG) {
      view.setUint16(entry + 8, 1, little)
      break
    }
  }
  return exif
}
