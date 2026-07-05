/**
 * Property-Based Tests — G4 债权投资(ECL组) 公式引擎
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Tasks 2.2 ~ 2.15
 * Framework: vitest + fast-check, numRuns ≥ 100
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcImpairmentProvision,
  calcBookValue,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  determineStage,
  isStageConsistent,
  isReversalValid,
  isDebitCreditBalanced,
  calcDebitCreditDifference,
  isVoucherNormal,
  calcSumColumn,
} from '../useG4EclFormulaEngine'

// ═══ Generators ═══
const amount = () => fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
const positiveAmount = () => fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })
const rate = () => fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true })
const amountArray = () => fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 0, maxLength: 50 })
const stageEnum = () => fc.constantFrom('Stage1' as const, 'Stage2' as const, 'Stage3' as const)

// ═══ Helper: round to 2 decimal places ═══
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══════════════════════════════════════════════════════════════════
// P1: 减值准备公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 1: 减值准备公式', () => {
  /**
   * **Validates: Requirements 8.1, 3.2**
   */
  it('calcImpairmentProvision(b, r) === round(b × r, 2) for b≥0, r∈[0,1]', () => {
    fc.assert(
      fc.property(
        positiveAmount(),
        rate(),
        (b, r) => {
          expect(calcImpairmentProvision(b, r)).toBe(round2(b * r))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P2: 账面价值恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 2: 账面价值恒等', () => {
  /**
   * **Validates: Requirements 8.2, 3.3**
   */
  it('calcBookValue(b, i) === round(b - i, 2) for b≥0, i≤b', () => {
    fc.assert(
      fc.property(
        positiveAmount(),
        rate(),
        (b, ratio) => {
          const i = b * ratio // ensure i ≤ b
          expect(calcBookValue(b, i)).toBe(round2(b - i))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P3: 审计调整公式链一致性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 3: 审计调整公式链一致性', () => {
  /**
   * **Validates: Requirements 8.3, 8.4, 8.5, 8.6, 3.4, 3.5, 3.6, 3.7**
   */
  it('full chain ⑨ = ⑦ - ⑧ holds for all inputs', () => {
    fc.assert(
      fc.property(
        amount(), // ① origBalance
        rate(),   // ② origRate
        amount(), // ⑤ balanceAdj
        rate(),   // ②A adjRate
        (origBal, origRate, balAdj, adjRate) => {
          // Compute through the chain
          const provision = calcImpairmentProvision(origBal, origRate) // ③
          const impAdj = calcImpairmentAdjustment(balAdj, adjRate, origBal, origRate) // ⑥
          const adjBalance = calcAdjustedBalance(origBal, balAdj) // ⑦
          const adjImpairment = calcAdjustedImpairment(provision, impAdj) // ⑧
          const adjBookValue = calcAdjustedBookValue(adjBalance, adjImpairment) // ⑨

          // Expected: ⑨ = (①+⑤) - (①×② + ⑤×②A + ①×(②A-②))
          const expected = round2(
            (origBal + balAdj) - (origBal * origRate + balAdj * adjRate + origBal * (adjRate - origRate)),
          )

          // Allow for floating point rounding differences (chain applies round2 at each step)
          expect(Math.abs(adjBookValue - expected)).toBeLessThanOrEqual(0.02)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P4: 减值准备调整公式展开
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 4: 减值准备调整公式展开', () => {
  /**
   * **Validates: Requirements 8.3, 3.4**
   */
  it('calcImpairmentAdjustment(ba, ar, ob, or) === round(ba×ar + ob×(ar-or), 2)', () => {
    fc.assert(
      fc.property(
        amount(),
        rate(),
        amount(),
        rate(),
        (ba, ar, ob, or_) => {
          expect(calcImpairmentAdjustment(ba, ar, ob, or_)).toBe(
            round2(ba * ar + ob * (ar - or_)),
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P5: 三阶段划分确定性与优先级
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 5: 三阶段划分确定性与优先级', () => {
  /**
   * **Validates: Requirements 8.7, 2.2**
   */
  it('creditImpaired=true → Stage3 always (highest priority)', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.boolean(),
        (sigIncrease, lowRisk) => {
          expect(determineStage(sigIncrease, lowRisk, true)).toBe('Stage3')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('significantIncrease=true, !creditImpaired → Stage2', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (lowRisk) => {
          expect(determineStage(true, lowRisk, false)).toBe('Stage2')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('!significantIncrease, !creditImpaired → Stage1', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (lowRisk) => {
          expect(determineStage(false, lowRisk, false)).toBe('Stage1')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P6: Stage1必要条件
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 6: Stage1必要条件', () => {
  /**
   * **Validates: Requirements 8.7, 2.2**
   */
  it('determineStage(...)===Stage1 → !hasSignificantIncrease AND !hasCreditImpairment', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.boolean(),
        fc.boolean(),
        (sigIncrease, lowRisk, creditImpaired) => {
          const result = determineStage(sigIncrease, lowRisk, creditImpaired)
          if (result === 'Stage1') {
            expect(sigIncrease).toBe(false)
            expect(creditImpaired).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P7: 阶段一致性判定
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 7: 阶段一致性判定', () => {
  /**
   * **Validates: Requirements 8.8, 2.3**
   */
  it('isStageConsistent(s1, s2) ↔ (s1 === s2)', () => {
    fc.assert(
      fc.property(
        stageEnum(),
        stageEnum(),
        (s1, s2) => {
          expect(isStageConsistent(s1, s2)).toBe(s1 === s2)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P8: 转回有效性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 8: 转回有效性', () => {
  /**
   * **Validates: Requirements 8.9, 5.2**
   */
  it('isReversalValid(r, a) ↔ (r ≤ a) for r≥0, a≥0', () => {
    fc.assert(
      fc.property(
        positiveAmount(),
        positiveAmount(),
        (r, a) => {
          expect(isReversalValid(r, a)).toBe(r <= a)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P9: 借贷平衡恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 9: 借贷平衡恒等', () => {
  /**
   * **Validates: Requirements 8.10, 8.11, 6.6**
   */
  it('isDebitCreditBalanced(d, c) ↔ |SUM(d)-SUM(c)| < 0.01', () => {
    fc.assert(
      fc.property(
        amountArray(),
        amountArray(),
        (d, c) => {
          const sumD = d.reduce((s, v) => s + v, 0)
          const sumC = c.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(d, c)).toBe(Math.abs(sumD - sumC) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcDebitCreditDifference(d, c) === round(SUM(d)-SUM(c), 2)', () => {
    fc.assert(
      fc.property(
        amountArray(),
        amountArray(),
        (d, c) => {
          const sumD = d.reduce((s, v) => s + v, 0)
          const sumC = c.reduce((s, v) => s + v, 0)
          expect(calcDebitCreditDifference(d, c)).toBe(round2(sumD - sumC))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P10: 凭证异常判定完备性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 10: 凭证异常判定完备性', () => {
  /**
   * **Validates: Requirements 8.12, 6.7**
   */
  it('isVoucherNormal(checks) ↔ all 6 checks are true', () => {
    fc.assert(
      fc.property(
        fc.array(fc.boolean(), { minLength: 6, maxLength: 6 }),
        (checks) => {
          expect(isVoucherNormal(checks)).toBe(checks.every(c => c === true))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P11: 合计行加法交换律
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 11: 合计行加法交换律', () => {
  /**
   * **Validates: Requirements 8.13**
   */
  it('calcSumColumn(v) === calcSumColumn(shuffle(v))', () => {
    fc.assert(
      fc.property(
        amountArray(),
        (values) => {
          // Fisher-Yates shuffle
          const shuffled = [...values]
          for (let i = shuffled.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
          }
          // Floating point addition is NOT truly commutative, but the sums should be very close
          expect(Math.abs(calcSumColumn(values) - calcSumColumn(shuffled))).toBeLessThan(0.001)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P12: parseNum健壮性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 12: parseNum健壮性', () => {
  /**
   * **Validates: Requirements 8.14**
   */
  it('parseNum(null/undefined/\'\'/NaN) === 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum('  ')).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('∀ finite n: parseNum(n) === n', () => {
    fc.assert(
      fc.property(
        fc.float({ noNaN: true, noDefaultInfinity: true }),
        (n) => {
          expect(parseNum(n)).toBe(n)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P13: 审定减值准备组合恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 13: 审定减值准备组合恒等', () => {
  /**
   * **Validates: Requirements 8.5, 8.3**
   */
  it('calcAdjustedImpairment(③, ⑥) === round(①×② + ⑤×②A + ①×(②A-②), 2)', () => {
    fc.assert(
      fc.property(
        amount(), // ①
        rate(),   // ②
        amount(), // ⑤
        rate(),   // ②A
        (origBal, origRate, balAdj, adjRate) => {
          const provision = calcImpairmentProvision(origBal, origRate) // ③
          const impAdj = calcImpairmentAdjustment(balAdj, adjRate, origBal, origRate) // ⑥
          const result = calcAdjustedImpairment(provision, impAdj) // ⑧ = ③ + ⑥

          const expected = round2(origBal * origRate + balAdj * adjRate + origBal * (adjRate - origRate))

          // Allow for intermediate rounding differences (each step rounds to 2dp)
          expect(Math.abs(result - expected)).toBeLessThanOrEqual(0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P14: 审定账面余额=原值+调整
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-ecl, Property 14: 审定账面余额=原值+调整', () => {
  /**
   * **Validates: Requirements 8.4, 3.5**
   */
  it('calcAdjustedBalance(o, b) === round(o + b, 2)', () => {
    fc.assert(
      fc.property(
        amount(),
        amount(),
        (o, b) => {
          expect(calcAdjustedBalance(o, b)).toBe(round2(o + b))
        },
      ),
      { numRuns: 100 },
    )
  })
})
