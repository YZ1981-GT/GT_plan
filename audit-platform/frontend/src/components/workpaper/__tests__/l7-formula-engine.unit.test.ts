/**
 * 单元测试 — L7 其他非流动负债公式引擎 useL7FormulaEngine
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 7.1
 * Requirements: P1-P5
 *
 * 覆盖：
 * - calcAuditedAmount: positive/negative/zero
 * - calcLiabilityEndBalance: 负债类方向(begin+credit-debit), edge cases
 * - calcSubtotal: empty/single/multiple
 * - calcVariance: positive/negative change
 * - calcVarianceRate: zero/zero, zero/positive, normal (xlsx formula)
 * - calcDetailEndBalance: same logic different naming
 * - validateAdjudicationVsDetail: match/mismatch
 * - NaN/undefined/null handling (safe() behavior)
 *
 * 科目：2801 其他非流动负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcVariance,
  calcVarianceRate,
  calcDetailEndBalance,
  validateAdjudicationVsDetail,
} from '../composables/useL7FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. calcAuditedAmount
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAuditedAmount', () => {
  it('positive values: 审定数=未审+AJE+RJE', () => {
    expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
  })

  it('negative adjustments: AJE调减', () => {
    expect(calcAuditedAmount(5000, -800, 0)).toBe(4200)
  })

  it('all zeros', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('negative unadjusted (unusual but valid)', () => {
    expect(calcAuditedAmount(-100, 50, 30)).toBe(-20)
  })

  it('large values (百万级)', () => {
    expect(calcAuditedAmount(50_000_000, 1_200_000, -300_000)).toBe(50_900_000)
  })

  it('NaN treated as 0 via safe()', () => {
    expect(calcAuditedAmount(NaN, 100, 50)).toBe(150)
    expect(calcAuditedAmount(1000, NaN, NaN)).toBe(1000)
  })

  it('undefined/null treated as 0 via safe()', () => {
    expect(calcAuditedAmount(undefined as any, 100, 50)).toBe(150)
    expect(calcAuditedAmount(1000, null as any, 0)).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. calcLiabilityEndBalance — 负债类方向（贷方！）
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcLiabilityEndBalance (负债类期末=期初+贷方-借方)', () => {
  it('basic: begin + credit - debit', () => {
    // 期初100万 + 贷方(增加)50万 - 借方(减少)20万 = 130万
    expect(calcLiabilityEndBalance(1_000_000, 500_000, 200_000)).toBe(1_300_000)
  })

  it('no movement: credit=0, debit=0 → 期末=期初', () => {
    expect(calcLiabilityEndBalance(500_000, 0, 0)).toBe(500_000)
  })

  it('debit exceeds begin+credit → negative (异常但公式正确)', () => {
    // 期初10 + 贷方5 - 借方20 = -5
    expect(calcLiabilityEndBalance(10, 5, 20)).toBe(-5)
  })

  it('begin=0, only credit → 新增负债', () => {
    expect(calcLiabilityEndBalance(0, 300_000, 0)).toBe(300_000)
  })

  it('全部清偿: debit=begin+credit → 期末=0', () => {
    expect(calcLiabilityEndBalance(500, 200, 700)).toBe(0)
  })

  it('NaN/undefined handling', () => {
    expect(calcLiabilityEndBalance(NaN, 100, 50)).toBe(50)
    expect(calcLiabilityEndBalance(1000, undefined as any, null as any)).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. calcSubtotal
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcSubtotal', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single item', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('multiple items', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
  })

  it('mixed positive/negative', () => {
    expect(calcSubtotal([1000, -200, 500, -100])).toBe(1200)
  })

  it('NaN in array treated as 0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('undefined/null in array treated as 0', () => {
    expect(calcSubtotal([100, undefined as any, null as any, 200])).toBe(300)
  })

  it('non-array input → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. calcVariance
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcVariance', () => {
  it('positive change: 本期增加', () => {
    expect(calcVariance(1500, 1000)).toBe(500)
  })

  it('negative change: 本期减少', () => {
    expect(calcVariance(800, 1200)).toBe(-400)
  })

  it('no change', () => {
    expect(calcVariance(1000, 1000)).toBe(0)
  })

  it('NaN handling', () => {
    expect(calcVariance(NaN, 100)).toBe(-100)
    expect(calcVariance(500, NaN)).toBe(500)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. calcVarianceRate — xlsx公式逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcVarianceRate (xlsx: IF(AND(E=0,J=0),0,IF(AND(E=0,J>0),1,J/E)))', () => {
  it('zero/zero → 0 (无变动)', () => {
    expect(calcVarianceRate(0, 0)).toBe(0)
  })

  it('zero previous, positive current → 1 (100%增长)', () => {
    expect(calcVarianceRate(500, 0)).toBe(1)
  })

  it('normal case: current/previous', () => {
    // 本期1200 / 上期1000 = 1.2 (增长20%)
    expect(calcVarianceRate(1200, 1000)).toBeCloseTo(1.2, 5)
  })

  it('decrease: current < previous', () => {
    // 本期600 / 上期1000 = 0.6
    expect(calcVarianceRate(600, 1000)).toBeCloseTo(0.6, 5)
  })

  it('zero previous, negative current → protective (J/1 fallback)', () => {
    // 上期=0, 本期<0 → c / 1 = current保护
    expect(calcVarianceRate(-200, 0)).toBe(-200)
  })

  it('NaN handling', () => {
    // safe(NaN) = 0, so calcVarianceRate(0, 0) = 0
    expect(calcVarianceRate(NaN, 100)).toBeCloseTo(0, 5)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6. calcDetailEndBalance — 明细表版本
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcDetailEndBalance (明细表期末=期初+增加-减少)', () => {
  it('basic: begin + increase - decrease', () => {
    expect(calcDetailEndBalance(1000, 300, 100)).toBe(1200)
  })

  it('no movement', () => {
    expect(calcDetailEndBalance(500, 0, 0)).toBe(500)
  })

  it('same logic as calcLiabilityEndBalance with different naming', () => {
    const b = 2_000_000
    const inc = 800_000
    const dec = 300_000
    // 两者逻辑相同
    expect(calcDetailEndBalance(b, inc, dec)).toBe(calcLiabilityEndBalance(b, inc, dec))
  })

  it('NaN/null handling', () => {
    expect(calcDetailEndBalance(NaN, 100, null as any)).toBe(100)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7. validateAdjudicationVsDetail — 审定vs明细勾稽
// ═══════════════════════════════════════════════════════════════════════════════

describe('validateAdjudicationVsDetail', () => {
  it('match: adjTotal === detailTotal → isMatch=true, diff=0', () => {
    const result = validateAdjudicationVsDetail(5_000_000, 5_000_000)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
  })

  it('mismatch: adjTotal > detailTotal → positive diff', () => {
    const result = validateAdjudicationVsDetail(5_000_000, 4_500_000)
    expect(result.isMatch).toBe(false)
    expect(result.diff).toBe(500_000)
  })

  it('mismatch: adjTotal < detailTotal → negative diff', () => {
    const result = validateAdjudicationVsDetail(3_000_000, 3_200_000)
    expect(result.isMatch).toBe(false)
    expect(result.diff).toBe(-200_000)
  })

  it('both zero → match', () => {
    const result = validateAdjudicationVsDetail(0, 0)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
  })

  it('NaN/null treated as 0', () => {
    const result = validateAdjudicationVsDetail(NaN, null as any)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
  })
})
