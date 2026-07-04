/**
 * useF2Adjustment — 借贷平衡单元测试
 */
import { describe, it, expect } from 'vitest'
import { isDebitCreditBalanced, calcSubtotal } from '../useF2InvMaiFormulaEngine'

describe('useF2Adjustment balance', () => {
  it('isDebitCreditBalanced returns true when debits equal credits', () => {
    expect(isDebitCreditBalanced([100, 50], [80, 70])).toBe(true)
  })

  it('isDebitCreditBalanced returns false when unbalanced', () => {
    expect(isDebitCreditBalanced([100], [50])).toBe(false)
  })

  it('calcSubtotal sums adjustment rows', () => {
    const debits = [1000, 500, 0]
    const credits = [800, 700, 0]
    expect(calcSubtotal(debits)).toBe(1500)
    expect(calcSubtotal(debits) - calcSubtotal(credits)).toBe(0)
  })
})
