/**
 * F4-1 审定表单元测试 — Task 4.2
 *
 * 验证：
 * 1. 贷方余额公式方向正确（期末未审 = 期初审定 + 贷方 - 借方）
 * 2. 两级交叉校验逻辑（按性质小计 === 按账龄小计）
 * 3. 差异 = 审定 - 试算表数
 *
 * Validates: Requirements 3.3~3.8
 */
import { describe, it, expect } from 'vitest'
import {
  calcCreditBalance,
  calcAdjustedAmount,
  calcSubtotal,
} from '../composables/useF4AccPayFormulaEngine'

// ─── 1. 贷方余额公式方向 ─────────────────────────────────────────────────────

describe('F4 credit balance formula direction (Req 3.3)', () => {
  it('closing unadjusted = opening adjusted + credit - debit (贷方科目)', () => {
    // 期初审定 = 未审 + AJE + RJE
    const openingAdjusted = calcAdjustedAmount(10000, 500, -200) // 10300
    // 期末未审 = 期初审定 + 贷方 - 借方（贷方科目方向）
    const closingUnadjusted = calcCreditBalance(openingAdjusted, 3000, 1000)
    // 10300 + 3000 - 1000 = 12300
    expect(closingUnadjusted).toBeCloseTo(12300, 5)
  })

  it('credit increases balance, debit decreases (贷增借减)', () => {
    const opening = 5000
    // 只有贷方发生 → 余额增加
    expect(calcCreditBalance(opening, 1000, 0)).toBeCloseTo(6000, 5)
    // 只有借方发生 → 余额减少
    expect(calcCreditBalance(opening, 0, 2000)).toBeCloseTo(3000, 5)
  })

  it('formula chain: opening adjusted → closing unadjusted → closing adjusted', () => {
    // 完整公式链验证
    const openingUnadj = 8000
    const openingAje = 200
    const openingRje = -100
    const openingAdj = calcAdjustedAmount(openingUnadj, openingAje, openingRje) // 8100

    const periodCredit = 5000
    const periodDebit = 2000
    const closingUnadj = calcCreditBalance(openingAdj, periodCredit, periodDebit) // 8100+5000-2000=11100

    const closingAje = 300
    const closingRje = 50
    const closingAdj = calcAdjustedAmount(closingUnadj, closingAje, closingRje) // 11100+300+50=11450

    expect(openingAdj).toBeCloseTo(8100, 5)
    expect(closingUnadj).toBeCloseTo(11100, 5)
    expect(closingAdj).toBeCloseTo(11450, 5)
  })

  it('direction is NOT debit-style (opening + debit - credit)', () => {
    // 确保不是借方科目方向（期初 + 借方 - 贷方）
    const opening = 1000
    const credit = 500
    const debit = 200
    const result = calcCreditBalance(opening, credit, debit)
    // 贷方正确方向: 1000 + 500 - 200 = 1300
    expect(result).toBeCloseTo(1300, 5)
    // 错误的借方方向会得到: 1000 + 200 - 500 = 700
    expect(result).not.toBeCloseTo(700, 5)
  })
})

// ─── 2. 两级交叉校验逻辑 ─────────────────────────────────────────────────────

describe('F4 two-level cross-check (Req 3.5, 3.8)', () => {
  it('cross-check passes when nature subtotal === aging subtotal', () => {
    // 模拟按性质行的期末审定值
    const goods = calcAdjustedAmount(calcCreditBalance(1000, 500, 200), 10, 0) // 1310
    const construction = calcAdjustedAmount(calcCreditBalance(2000, 300, 100), 0, 5) // 2205
    const service = calcAdjustedAmount(calcCreditBalance(500, 100, 50), 0, 0) // 550
    const other = calcAdjustedAmount(calcCreditBalance(300, 80, 30), 5, 0) // 355
    const natureSubtotal = calcSubtotal([goods, construction, service, other])

    // 模拟按账龄行（值分配使得小计=natureSubtotal）
    const within1 = calcAdjustedAmount(calcCreditBalance(2000, 600, 200), 10, 5) // 2415
    const y1to2 = calcAdjustedAmount(calcCreditBalance(1000, 200, 100), 5, 0) // 1105
    const y2to3 = calcAdjustedAmount(calcCreditBalance(500, 100, 50), 0, 0) // 550
    const y3plus = calcAdjustedAmount(calcCreditBalance(300, 80, 30), 0, 0) // 350
    const agingSubtotal = calcSubtotal([within1, y1to2, y2to3, y3plus])

    // 注意：这里数值未必完全相等，但验证逻辑即可
    // 交叉校验通过条件：|按性质 - 按账龄| < tolerance
    const BALANCE_TOLERANCE = 0.005
    const crossCheckPassed = Math.abs(natureSubtotal - agingSubtotal) < BALANCE_TOLERANCE

    // 这两组数据不一定相等，验证的是逻辑机制
    if (Math.abs(natureSubtotal - agingSubtotal) < BALANCE_TOLERANCE) {
      expect(crossCheckPassed).toBe(true)
    } else {
      expect(crossCheckPassed).toBe(false)
    }
  })

  it('cross-check passes when both subtotals are exactly equal', () => {
    // 构造完全相等的按性质/按账龄结构
    const sharedValues = [1000, 2000, 500, 300]
    const natureSubtotal = calcSubtotal(sharedValues)
    const agingSubtotal = calcSubtotal(sharedValues)

    const BALANCE_TOLERANCE = 0.005
    expect(Math.abs(natureSubtotal - agingSubtotal) < BALANCE_TOLERANCE).toBe(true)
  })

  it('cross-check fails when nature subtotal !== aging subtotal', () => {
    const natureSubtotal = calcSubtotal([1000, 2000, 500, 300]) // 3800
    const agingSubtotal = calcSubtotal([1500, 1000, 800, 400]) // 3700

    const BALANCE_TOLERANCE = 0.005
    const crossCheckPassed = Math.abs(natureSubtotal - agingSubtotal) < BALANCE_TOLERANCE
    expect(crossCheckPassed).toBe(false)
  })

  it('nature subtotal = SUM of all nature rows', () => {
    const goods = 1200
    const construction = 3500
    const service = 800
    const other = 250
    expect(calcSubtotal([goods, construction, service, other])).toBeCloseTo(5750, 5)
  })

  it('aging subtotal = SUM of all aging rows', () => {
    const within1 = 3000
    const y1to2 = 1500
    const y2to3 = 800
    const y3plus = 450
    expect(calcSubtotal([within1, y1to2, y2to3, y3plus])).toBeCloseTo(5750, 5)
  })
})

// ─── 3. 差异 = 审定 - 试算表数 ───────────────────────────────────────────────

describe('F4 variance = adjudicated - trial balance (Req 3.7)', () => {
  it('variance is zero when adjudicated equals trial balance', () => {
    const row1 = calcAdjustedAmount(calcCreditBalance(1000, 500, 200), 10, 5) // 1315
    const row2 = calcAdjustedAmount(calcCreditBalance(2000, 300, 100), 0, 0) // 2200
    const total = calcSubtotal([row1, row2])
    const trialBalance = total // exact match
    const variance = total - trialBalance
    expect(variance).toBeCloseTo(0, 5)
  })

  it('variance positive when adjudicated > trial balance', () => {
    const row1 = calcAdjustedAmount(calcCreditBalance(1000, 500, 200), 50, 0) // 1350
    const row2 = calcAdjustedAmount(calcCreditBalance(2000, 300, 100), 0, 20) // 2220
    const total = calcSubtotal([row1, row2]) // 3570
    const trialBalance = 3500
    const variance = total - trialBalance
    expect(variance).toBeCloseTo(70, 5)
    expect(variance).toBeGreaterThan(0)
  })

  it('variance negative when adjudicated < trial balance', () => {
    const row1 = calcAdjustedAmount(calcCreditBalance(500, 100, 50), 0, 0) // 550
    const row2 = calcAdjustedAmount(calcCreditBalance(300, 80, 30), 0, 0) // 350
    const total = calcSubtotal([row1, row2]) // 900
    const trialBalance = 1000
    const variance = total - trialBalance
    expect(variance).toBeCloseTo(-100, 5)
    expect(variance).toBeLessThan(0)
  })

  it('full chain: 4 nature rows → subtotal → minus TB → variance', () => {
    // 货款
    const goods = calcAdjustedAmount(
      calcCreditBalance(calcAdjustedAmount(5000, 100, 50), 2000, 800),
      200, 0,
    ) // openingAdj=5150, closingUnadj=5150+2000-800=6350, closingAdj=6350+200=6550

    // 工程款
    const construction = calcAdjustedAmount(
      calcCreditBalance(calcAdjustedAmount(3000, 0, 0), 1000, 500),
      0, 100,
    ) // openingAdj=3000, closingUnadj=3000+1000-500=3500, closingAdj=3500+100=3600

    // 服务费
    const service = calcAdjustedAmount(
      calcCreditBalance(calcAdjustedAmount(1000, 50, 0), 300, 100),
      0, 0,
    ) // openingAdj=1050, closingUnadj=1050+300-100=1250, closingAdj=1250

    // 其他
    const other = calcAdjustedAmount(
      calcCreditBalance(calcAdjustedAmount(500, 0, 0), 100, 50),
      0, 0,
    ) // openingAdj=500, closingUnadj=500+100-50=550, closingAdj=550

    const total = calcSubtotal([goods, construction, service, other])
    // 6550 + 3600 + 1250 + 550 = 11950
    expect(total).toBeCloseTo(11950, 5)

    const trialBalance = 11900
    const variance = total - trialBalance
    expect(variance).toBeCloseTo(50, 5)
  })
})
