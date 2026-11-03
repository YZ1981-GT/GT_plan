import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAdjustedAmount,
  calcNetImpairmentLoss,
  calcProvisionRollForward,
  calcChangeRate,
  isDebitCreditBalanced,
  isRollForwardBalanced,
  isReconciled,
} from '../useG14FormulaEngine'
import { enrichRow } from '../useG14Detail'

describe('useG14FormulaEngine', () => {
  it('calcAdjustedAmount', () => {
    expect(calcAdjustedAmount(100, 20)).toBe(120)
  })

  it('calcNetImpairmentLoss（转回正数）', () => {
    expect(calcNetImpairmentLoss(50, 10)).toBe(40)
  })

  it('calcProvisionRollForward（转回正数 + 其他变动）', () => {
    // 100 + 30 - 5 - 10 + 2 = 117
    expect(calcProvisionRollForward(100, 30, 5, 10, 2)).toBe(117)
  })

  it('calcChangeRate null when prior zero', () => {
    expect(calcChangeRate(0, 100)).toBeNull()
  })

  it('isDebitCreditBalanced', () => {
    expect(isDebitCreditBalanced([100, 50], [150])).toBe(true)
  })

  it('parseNum invalid', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('abc')).toBe(0)
  })

  it('isRollForwardBalanced', () => {
    expect(isRollForwardBalanced(100, 30, 5, 10, 117, 2)).toBe(true)
    expect(isRollForwardBalanced(100, 30, 5, 10, 200, 2)).toBe(false)
  })

  it('计入损益与滚动在转回为正时一致', () => {
    const provision = 100
    const reversal = 20
    const profitLoss = calcNetImpairmentLoss(provision, reversal)
    const closing = calcProvisionRollForward(500, provision, reversal, 10)
    expect(profitLoss).toBe(80)
    expect(closing).toBe(570)
  })

  it('转回按录入值计算，载入时不改号（与模板 J=F+G-H-I、K=G-H 同）', () => {
    const row = enrichRow({
      rowKey: 'notes', openingProvision: 500, currentProvision: 100, currentReversal: -20, currentWriteoff: 10,
    })
    expect(row.currentReversal).toBe(-20)
    expect(row.profitLoss).toBe(120)
    expect(row.closingProvision).toBe(610)
  })

  it('核对按分相等：差一分不平（原 |差|≤0.01 会因浮点尾差判平）', () => {
    expect(isReconciled(0.1 + 0.2, 0.3)).toBe(true)
    expect(isReconciled(-239135.95999999996, -239135.95)).toBe(false)
    expect(isReconciled(100, 100.01)).toBe(false)
  })
})
