/**
 * Property-Based Tests — G7 长期股权投资(权益法组) 公式引擎
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/ Tasks 1.3 ~ 1.11
 * Framework: vitest + fast-check, numRuns: 100
 *
 * 9 Properties covering all 9 pure functions + parseNum:
 *   P1: calcInvestmentCost  — 初始投资成本 = 支付对价 + 直接费用
 *   P2: calcShareOfNetAssets — 享有份额 = 净资产FV × 持股比例
 *   P3: calcGoodwill — 商誉/营业外 = 初始成本 - 享有份额
 *   P4: calcAdjustedNetProfit — 调整后净利润 = r - i - f + p + o
 *   P5: calcEquityShare — 持股份额 = 值 × 比例
 *   P6: calcEquityMethodBalance — 余额递推 = o + i + oci + eq - d
 *   P7: calcEliminationAmount — 顺流全额 / 逆流按比例
 *   P8: calcImpairmentAmount — MAX(0, 账面-可收回) 且 ≥ 0
 *   P9: parseNum — 无效→0; 有效finite→原值
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcInvestmentCost,
  calcShareOfNetAssets,
  calcGoodwill,
  calcAdjustedNetProfit,
  calcEquityShare,
  calcEquityMethodBalance,
  calcEliminationAmount,
  calcImpairmentAmount,
} from '../useG7EquityMethodFormulaEngine'

// ═══ Generators ═══
const amountArb = () => fc.double({ noNaN: true, noDefaultInfinity: true, min: -1e6, max: 1e6 })
const ratioArb = () => fc.double({ noNaN: true, noDefaultInfinity: true, min: 0, max: 1 })
const directionArb = () => fc.constantFrom('downstream' as const, 'upstream' as const)

// ═══ Helper: independent round to 2 decimal places ═══
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══════════════════════════════════════════════════════════════════
// P1: 初始投资成本公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 1: 初始投资成本公式', () => {
  /**
   * **Validates: Requirements 4.2**
   */
  it('calcInvestmentCost(c, d) === round(c + d, 2) for all amounts', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (consideration, directCosts) => {
          expect(calcInvestmentCost(consideration, directCosts)).toBe(round2(consideration + directCosts))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P2: 享有净资产份额公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 2: 享有净资产份额公式', () => {
  /**
   * **Validates: Requirements 4.3**
   */
  it('calcShareOfNetAssets(fv, ratio) === round(fv × ratio, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        ratioArb(),
        (netAssetFV, ratio) => {
          expect(calcShareOfNetAssets(netAssetFV, ratio)).toBe(round2(netAssetFV * ratio))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P3: 商誉/营业外收入差额
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 3: 商誉/营业外收入差额', () => {
  /**
   * **Validates: Requirements 4.4**
   */
  it('calcGoodwill(cost, share) === round(cost - share, 2) for all amounts', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (initialCost, shareOfNetAssets) => {
          const result = calcGoodwill(initialCost, shareOfNetAssets)
          expect(result).toBe(round2(initialCost - shareOfNetAssets))
        },
      ),
      { numRuns: 100 },
    )
  })

  it('正值=商誉性质, 负值=营业外收入性质', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (initialCost, shareOfNetAssets) => {
          const result = calcGoodwill(initialCost, shareOfNetAssets)
          if (result > 0) {
            // 商誉: 初始成本 > 享有份额
            expect(round2(initialCost - shareOfNetAssets)).toBeGreaterThan(0)
          } else if (result < 0) {
            // 营业外收入: 初始成本 < 享有份额
            expect(round2(initialCost - shareOfNetAssets)).toBeLessThan(0)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P4: 调整后净利润公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 4: 调整后净利润公式', () => {
  /**
   * **Validates: Requirements 5.2**
   */
  it('calcAdjustedNetProfit(r, i, f, p, o) === round(r - i - f + p + o, 2) for all amounts', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        amountArb(),
        amountArb(),
        amountArb(),
        (reported, internalTrans, fvDepreciation, policyAdj, other) => {
          expect(calcAdjustedNetProfit(reported, internalTrans, fvDepreciation, policyAdj, other))
            .toBe(round2(reported - internalTrans - fvDepreciation + policyAdj + other))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P5: 持股比例份额通用乘法
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 5: 持股比例份额通用乘法', () => {
  /**
   * **Validates: Requirements 5.3, 5.5, 5.6**
   */
  it('calcEquityShare(val, ratio) === round(val × ratio, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        ratioArb(),
        (value, ratio) => {
          expect(calcEquityShare(value, ratio)).toBe(round2(value * ratio))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P6: 权益法余额递推
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 6: 权益法余额递推', () => {
  /**
   * **Validates: Requirements 5.7**
   */
  it('calcEquityMethodBalance(o, i, oci, eq, d) === round(o + i + oci + eq - d, 2) for all amounts', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        amountArb(),
        amountArb(),
        amountArb(),
        (opening, income, oci, equityChange, dividend) => {
          expect(calcEquityMethodBalance(opening, income, oci, equityChange, dividend))
            .toBe(round2(opening + income + oci + equityChange - dividend))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P7: 内部交易抵销顺流/逆流
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 7: 内部交易抵销顺流/逆流', () => {
  /**
   * **Validates: Requirements 6.3**
   */
  it('downstream: calcEliminationAmount === round(profit, 2) 全额', () => {
    fc.assert(
      fc.property(
        amountArb(),
        ratioArb(),
        (profit, ratio) => {
          expect(calcEliminationAmount('downstream', profit, ratio)).toBe(round2(profit))
        },
      ),
      { numRuns: 100 },
    )
  })

  it('upstream: calcEliminationAmount === round(profit × ratio, 2) 按份额', () => {
    fc.assert(
      fc.property(
        amountArb(),
        ratioArb(),
        (profit, ratio) => {
          expect(calcEliminationAmount('upstream', profit, ratio)).toBe(round2(profit * ratio))
        },
      ),
      { numRuns: 100 },
    )
  })

  it('direction差异化: 顺流结果 ≥ 逆流结果 (非负利润时)', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true, min: 0, max: 1e6 }),
        ratioArb(),
        (profit, ratio) => {
          const downstream = calcEliminationAmount('downstream', profit, ratio)
          const upstream = calcEliminationAmount('upstream', profit, ratio)
          expect(downstream).toBeGreaterThanOrEqual(upstream)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P8: 减值非负 + MAX语义
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 8: 减值非负+MAX语义', () => {
  /**
   * **Validates: Requirements 6.6**
   */
  it('calcImpairmentAmount(bv, ra) === round(MAX(0, bv - ra), 2) for all amounts', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (bookValue, recoverableAmount) => {
          const expected = round2(Math.max(0, bookValue - recoverableAmount))
          expect(calcImpairmentAmount(bookValue, recoverableAmount)).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('结果永远 ≥ 0 (非负性质)', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (bookValue, recoverableAmount) => {
          expect(calcImpairmentAmount(bookValue, recoverableAmount)).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P9: parseNum 健壮性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-method, Property 9: parseNum健壮性', () => {
  /**
   * **Validates: Requirements 7.1**
   */
  const invalidArb = () => fc.oneof(
    fc.constant(null),
    fc.constant(undefined),
    fc.constant(''),
    fc.constant('  '),
    fc.constant('abc'),
    fc.constant('12.3.4'),
    fc.constant(NaN),
    fc.constant(Infinity),
    fc.constant(-Infinity),
    fc.constant('hello world'),
    fc.constant('not_a_number'),
    fc.constant('$$'),
  )

  const finiteArb = () => fc.double({ noNaN: true, noDefaultInfinity: true, min: -1e6, max: 1e6 })

  it('无效输入 → 0', () => {
    fc.assert(
      fc.property(
        invalidArb(),
        (v) => {
          expect(parseNum(v)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('有效finite数字 → 原值透传', () => {
    fc.assert(
      fc.property(
        finiteArb(),
        (n) => {
          expect(parseNum(n)).toBe(n)
        },
      ),
      { numRuns: 100 },
    )
  })
})
