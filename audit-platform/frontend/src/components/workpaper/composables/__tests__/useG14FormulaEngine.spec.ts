import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAdjustedAmount,
  calcNetImpairmentLoss,
  calcProvisionRollForward,
  calcChangeRate,
  isDebitCreditBalanced,
  isRollForwardBalanced,
} from '../useG14FormulaEngine'

describe('useG14FormulaEngine', () => {
  it('calcAdjustedAmount', () => {
    expect(calcAdjustedAmount(100, 20)).toBe(120)
  })

  it('calcNetImpairmentLoss', () => {
    expect(calcNetImpairmentLoss(50, 10)).toBe(40)
  })

  it('calcProvisionRollForward（转回带符号）', () => {
    expect(calcProvisionRollForward(100, 30, -5, 10)).toBe(115)
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
    expect(isRollForwardBalanced(100, 30, -5, 10, 115)).toBe(true)
    expect(isRollForwardBalanced(100, 30, -5, 10, 200)).toBe(false)
  })

  it('计入损益与滚动在转回为负时一致', () => {
    const provision = 100
    const reversalSigned = -20
    const profitLoss = provision + reversalSigned
    const closing = calcProvisionRollForward(500, provision, reversalSigned, 10)
    expect(profitLoss).toBe(80)
    expect(closing).toBe(570)
  })
})
