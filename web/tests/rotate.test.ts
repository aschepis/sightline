import { describe, expect, it } from 'vitest'
import { displaySize, rotationFromMatrix } from '../src/video/rotate'

const F = 65536

describe('rotationFromMatrix', () => {
  it('reads the common phone matrices', () => {
    expect(rotationFromMatrix([F, 0, 0, 0, F, 0, 0, 0, 0x40000000])).toBe(0)
    expect(rotationFromMatrix([0, F, 0, -F, 0, 0, 0, 0, 0x40000000])).toBe(90)
    expect(rotationFromMatrix([-F, 0, 0, 0, -F, 0, 0, 0, 0x40000000])).toBe(180)
    expect(rotationFromMatrix([0, -F, 0, F, 0, 0, 0, 0, 0x40000000])).toBe(270)
    expect(rotationFromMatrix(undefined)).toBe(0)
  })

  it('swaps dimensions for quarter turns', () => {
    expect(displaySize(640, 360, 90)).toEqual({ width: 360, height: 640 })
    expect(displaySize(640, 360, 180)).toEqual({ width: 640, height: 360 })
  })
})
