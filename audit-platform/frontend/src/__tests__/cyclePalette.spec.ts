import { describe, it, expect } from 'vitest'
import { CYCLE_PALETTE, cycleColor } from '@/constants/cyclePalette'

describe('cyclePalette 单一真源', () => {
  const ALL_CYCLES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'S']

  it('A~S 全覆盖：每个循环都有定义且为合法 hex', () => {
    for (const c of ALL_CYCLES) {
      expect(CYCLE_PALETTE[c], `${c} should be defined`).toBeDefined()
      expect(CYCLE_PALETTE[c]).toMatch(/^#[0-9A-Fa-f]{6}$/)
    }
  })

  it('other 兜底存在', () => {
    expect(CYCLE_PALETTE.other).toBeDefined()
    expect(CYCLE_PALETTE.other).toMatch(/^#[0-9A-Fa-f]{6}$/)
  })

  it('cycleColor 已知循环返回正确色值', () => {
    expect(cycleColor('D')).toBe(CYCLE_PALETTE.D)
    expect(cycleColor('H')).toBe(CYCLE_PALETTE.H)
    expect(cycleColor('S')).toBe(CYCLE_PALETTE.S)
  })

  it('cycleColor 大小写不敏感', () => {
    expect(cycleColor('d')).toBe(CYCLE_PALETTE.D)
    expect(cycleColor('h')).toBe(CYCLE_PALETTE.H)
  })

  it('cycleColor null/undefined/空 → other', () => {
    expect(cycleColor(null)).toBe(CYCLE_PALETTE.other)
    expect(cycleColor(undefined)).toBe(CYCLE_PALETTE.other)
    expect(cycleColor('')).toBe(CYCLE_PALETTE.other)
  })

  it('cycleColor 未知字母 → other', () => {
    expect(cycleColor('X')).toBe(CYCLE_PALETTE.other)
    expect(cycleColor('Z')).toBe(CYCLE_PALETTE.other)
    expect(cycleColor('AB')).toBe(CYCLE_PALETTE.other)
  })
})
