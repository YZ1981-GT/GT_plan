/**
 * isG8SheetComplete — 附注完成度（指定原因 + 审定勾稽；不含审计说明/结论）
 */
import { describe, it, expect } from 'vitest'
import { isG8SheetComplete } from '../g8SheetLabels'

function mapOf(entries: Record<string, { conclusion?: string | null; remark?: string | null }>) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) m.set(k, v)
  return m
}

const v2Store = (closing: number, designation: string) =>
  JSON.stringify({
    v: 2,
    balanceRows: [{ label: 'A', closing, prior: 0 }],
    designationText: designation,
  })

describe('isG8SheetComplete disclosure', () => {
  it('仅有 key 不算完成', () => {
    const m = mapOf({ 'G8-disclosure-listed': { remark: '{}' } })
    expect(isG8SheetComplete('附注上市', m)).toBe(false)
  })

  it('有金额无指定原因不算完成', () => {
    const m = mapOf({
      'G8-disclosure-listed': { remark: v2Store(100, '') },
      'G8-1-adjudicated-amount': { conclusion: '100' },
    })
    expect(isG8SheetComplete('附注上市', m)).toBe(false)
  })

  it('有指定原因但未勾稽不算完成', () => {
    const m = mapOf({
      'G8-disclosure-listed': { remark: v2Store(80, '战略持有') },
      'G8-1-adjudicated-amount': { conclusion: '100' },
    })
    expect(isG8SheetComplete('附注上市', m)).toBe(false)
  })

  it('指定原因 + 勾稽算完成（不要求审计结论）', () => {
    const m = mapOf({
      'G8-disclosure-listed': { remark: v2Store(100, '战略持有指定 FVOCI') },
      'G8-1-adjudicated-amount': { conclusion: '100' },
    })
    expect(isG8SheetComplete('附注上市', m)).toBe(true)
  })

  it('仅附注汇总不算完成', () => {
    const m = mapOf({
      'G8-disclosure-soe-note': { conclusion: '已核对披露' },
    })
    expect(isG8SheetComplete('附注国企', m)).toBe(false)
  })

  it('兼容旧扁平键（含 designation）+ 勾稽', () => {
    const m = mapOf({
      'G8-disclosure-listed': {
        remark: JSON.stringify({
          listed_bal_1: { currentAmount: 100, priorAmount: 0, noteText: '' },
          listed_designation: { noteText: '战略长期持有' },
        }),
      },
      'G8-1-adjudicated-amount': { conclusion: '100' },
    })
    expect(isG8SheetComplete('附注上市', m)).toBe(true)
  })
})
