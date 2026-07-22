import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAdjustedAmount,
  calcNetImpairmentLoss,
  calcProvisionRollForward,
  calcChangeRate,
  isDebitCreditBalanced,
  isRollForwardBalanced,
  migrateReversalToPositive,
} from '../useG14FormulaEngine'

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

  it('migrateReversalToPositive 兼容旧带符号数据', () => {
    expect(migrateReversalToPositive(-20)).toBe(20)
    expect(migrateReversalToPositive(15)).toBe(15)
  })
})
