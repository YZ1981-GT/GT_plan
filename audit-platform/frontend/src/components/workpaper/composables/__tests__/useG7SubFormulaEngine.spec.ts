/**
 * Property-Based Tests — G7 长期股权投资(子公司组) 公式引擎
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Tasks 1.2 ~ 1.9
 * Framework: vitest + fast-check, numRuns: 100
 *
 * 8 Properties covering all 7 pure functions + parseNum:
 *   P1: calcSameControlCost — 同控初始投资成本 = 净资产 × 持股比例
 *   P2: calcNotSameControlCost — 非同控初始投资成本 = 支付对价 + 直接费用
 *   P3: calcGoodwill — 商誉 = 初始成本 - 享有份额；正=商誉，负=营业外收入
 *   P4: calcCostMethodIncome — 成本法投资收益 = 宣告股利 × 持股比例
 *   P5: calcSubsequentBalance — 期末账面 = 期初 + 追加 - 减值
 *   P6: calcDisposalGain — 处置损益 = 对价 - 账面 - 应收股利 + OCI
 *   P7: isDebitCreditBalanced — 借贷平衡 ↔ |SUM(debits)-SUM(credits)| < 0.01
 *   P8: parseNum — 无效→0; 有效finite→原值
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcSameControlCost,
  calcNotSameControlCost,
  calcGoodwill,
  calcCostMethodIncome,
  calcSubsequentBalance,
  calcDisposalGain,
  isDebitCreditBalanced,
} from '../useG7SubFormulaEngine'

// ═══ Generators ═══
const amountArb = () => fc.float({ noNaN: true, noDefaultInfinity: true })
const ratioArb = () => fc.float({ noNaN: true, noDefaultInfinity: true, min: 0, max: 1 })

// ═══ Helper: independent round to 2 decimal places ═══
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══════════════════════════════════════════════════════════════════
// P1: 同控初始投资成本 = 被合并方账面净资产 × 持股比例
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 1: 同控初始投资成本', () => {
  /**
   * **Validates: Requirements 3.3**
   */
  it('calcSameControlCost(netAssets, ratio) === round(netAssets × ratio, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        ratioArb(),
        (netAssets, ratio) => {
          expect(calcSameControlCost(netAssets, ratio)).toBe(round2(netAssets * ratio))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P2: 非同控初始投资成本 = 支付对价 + 直接相关费用
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 2: 非同控初始投资成本', () => {
  /**
   * **Validates: Requirements 3.4**
   */
  it('calcNotSameControlCost(price, fees) === round(price + fees, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (price, fees) => {
          expect(calcNotSameControlCost(price, fees)).toBe(round2(price + fees))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P3: 商誉 = 初始投资成本 - 享有份额；正=商誉，负=营业外收入
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 3: 商誉计算及符号语义', () => {
  /**
   * **Validates: Requirements 3.4, 7.1**
   */
  it('calcGoodwill(cost, share) === round(cost - share, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (cost, share) => {
          expect(calcGoodwill(cost, share)).toBe(round2(cost - share))
        },
      ),
      { numRuns: 100 },
    )
  })

  it('正值=商誉, 负值=营业外收入(廉价购买利得)', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        (cost, share) => {
          const result = calcGoodwill(cost, share)
          if (result > 0) {
            expect(round2(cost - share)).toBeGreaterThan(0)
          } else if (result < 0) {
            expect(round2(cost - share)).toBeLessThan(0)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P4: 成本法投资收益 = 被投资方宣告股利 × 持股比例
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 4: 成本法投资收益', () => {
  /**
   * **Validates: Requirements 4.2**
   */
  it('calcCostMethodIncome(dividend, ratio) === round(dividend × ratio, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        ratioArb(),
        (dividend, ratio) => {
          expect(calcCostMethodIncome(dividend, ratio)).toBe(round2(dividend * ratio))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P5: 成本法期末账面余额 = 期初 + 追加投资 - 减值
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 5: 成本法期末账面余额', () => {
  /**
   * **Validates: Requirements 4.3**
   */
  it('calcSubsequentBalance(opening, addition, impairment) === round(opening + addition - impairment, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        amountArb(),
        (opening, addition, impairment) => {
          expect(calcSubsequentBalance(opening, addition, impairment)).toBe(round2(opening + addition - impairment))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P6: 处置损益 = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 6: 处置损益', () => {
  /**
   * **Validates: Requirements 5.3**
   */
  it('calcDisposalGain(price, bookValue, dividend, oci) === round(price - bookValue - dividend + oci, 2) for all inputs', () => {
    fc.assert(
      fc.property(
        amountArb(),
        amountArb(),
        amountArb(),
        amountArb(),
        (price, bookValue, dividend, oci) => {
          expect(calcDisposalGain(price, bookValue, dividend, oci)).toBe(round2(price - bookValue - dividend + oci))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P7: 借贷平衡恒等 — |SUM(debits) - SUM(credits)| < 0.01
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 7: 借贷平衡恒等', () => {
  /**
   * **Validates: Requirements 6.2, 7.1**
   */
  it('isDebitCreditBalanced(debits, credits) ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ noNaN: true, noDefaultInfinity: true }), { minLength: 0, maxLength: 10 }),
        fc.array(fc.float({ noNaN: true, noDefaultInfinity: true }), { minLength: 0, maxLength: 10 }),
        (debits, credits) => {
          const sumD = debits.reduce((s, v) => s + v, 0)
          const sumC = credits.reduce((s, v) => s + v, 0)
          const expected = Math.abs(sumD - sumC) < 0.01
          expect(isDebitCreditBalanced(debits, credits)).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P8: parseNum 健壮性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-subsidiary, Property 8: parseNum健壮性', () => {
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

  const finiteArb = () => fc.float({ noNaN: true, noDefaultInfinity: true })

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
