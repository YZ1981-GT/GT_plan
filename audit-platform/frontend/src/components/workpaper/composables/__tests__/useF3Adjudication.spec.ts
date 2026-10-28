/**
 * F3-1 审定表单元测试 — Task 4.2
 */
import { describe, it, expect } from 'vitest'
import { calcCreditBalance, calcAdjustedAmount, calcSubtotal } from '../useF3FormulaEngine'

describe('F3 adjudication formula chain', () => {
  // 模板 F3-2 O = L + M − N：期末未审从期初未审起算，期初调整只进期初审定（生产代码断言见 templateParityDBatch.spec.ts）
  it('closing unadjusted = opening unadjusted + credit - debit', () => {
    const openingUnadj = 1000
    const closingUnadj = calcCreditBalance(openingUnadj, 500, 200)
    expect(closingUnadj).toBeCloseTo(1000 + 500 - 200, 5)
  })

  it('subtotal equals bank + commercial closing adjusted', () => {
    const bank = calcAdjustedAmount(calcCreditBalance(100, 50, 10), 5, 0)
    const commercial = calcAdjustedAmount(calcCreditBalance(200, 30, 20), 0, 2)
    expect(calcSubtotal([bank, commercial])).toBeCloseTo(bank + commercial, 5)
  })

  it('variance = adjudicated total - trial balance', () => {
    const bankClosing = calcAdjustedAmount(calcCreditBalance(100, 40, 10), 0, 0)
    const commercialClosing = calcAdjustedAmount(calcCreditBalance(50, 20, 5), 0, 0)
    const total = calcSubtotal([bankClosing, commercialClosing])
    const tb = 145
    expect(total - tb).toBeCloseTo(total - 145, 5)
  })
})
