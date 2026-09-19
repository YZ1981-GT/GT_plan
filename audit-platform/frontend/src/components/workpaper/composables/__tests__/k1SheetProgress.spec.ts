import { describe, it, expect } from 'vitest'
import { calcK1SheetProgress } from '../k1SheetProgress'

describe('calcK1SheetProgress', () => {
  it('returns 0 when no matching keys', () => {
    expect(calcK1SheetProgress(new Map(), 'K1-1')).toBe(0)
  })

  it('returns 100 for K1 index sheet', () => {
    expect(calcK1SheetProgress(new Map(), 'K1')).toBe(100)
  })

  it('uses K1-1 prefix not duplicated K1-K1-1', () => {
    const map = new Map<string, any>([
      ['K1-1-receivable-r0-unadj', { remark: '1000' }],
      ['K1-1-receivable-r0-aje', { remark: '0' }],
      ['K1-1-receivable-r0-rje', { remark: '0' }],
    ])
    expect(calcK1SheetProgress(map, 'K1-1')).toBeGreaterThan(0)
  })

  it('returns 100 when enough fields filled', () => {
    const map = new Map<string, any>()
    for (let i = 0; i < 12; i++) {
      map.set(`K1-1-field-${i}`, { remark: 'x' })
    }
    expect(calcK1SheetProgress(map, 'K1-1')).toBe(100)
  })
})
