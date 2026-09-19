/**
 * Unit Tests — K2 其他流动资产 公式引擎 + 摊销引擎（边界/边缘情况）
 *
 * Spec: .kiro/specs/k2-other-current-assets/ Task 7.1
 * Requirements: CP-K2-01~06
 *
 * 与 k2FormulaEngine.pbt.spec.ts 互补：
 * - PBT 验证公式在随机输入下的数学正确性
 * - 本文件验证特定边界情况和边缘条件
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from '../composables/useK2FormulaEngine'
import {
  calcStraightLineAmort,
  calcProgressAmort,
  calcAmortizedBalance,
  calcAmortVariance,
} from '../composables/useK2AmortizationEngine'

// ============================================================
// useK2FormulaEngine
// ============================================================

// --- calcAuditedAmount: 审定数 = 未审 + AJE + RJE ---
describe('calcAuditedAmount', () => {
  it('basic sum: 100000 + 5000 + 2000 = 107000', () => {
    expect(calcAuditedAmount(100000, 5000, 2000)).toBe(107000)
  })

  it('all zeros → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('with negative AJE (调减)', () => {
    expect(calcAuditedAmount(50000, -10000, 0)).toBe(40000)
  })

  it('with negative RJE (重分类调出)', () => {
    expect(calcAuditedAmount(80000, 0, -30000)).toBe(50000)
  })

  it('both AJE and RJE negative', () => {
    expect(calcAuditedAmount(100000, -20000, -15000)).toBe(65000)
  })

  it('large numbers (亿级)', () => {
    expect(calcAuditedAmount(1_000_000_000, 500_000, -200_000)).toBe(1_000_300_000)
  })

  it('fractional precision (分)', () => {
    expect(calcAuditedAmount(100.01, 0.99, 0)).toBeCloseTo(101, 5)
  })
})

// --- calcAssetEndBalance: 资产类期末 = 期初 + 借方 - 贷方 ---
describe('calcAssetEndBalance', () => {
  it('basic: 100000 + 20000 - 5000 = 115000', () => {
    expect(calcAssetEndBalance(100000, 20000, 5000)).toBe(115000)
  })

  it('all zeros → 0', () => {
    expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
  })

  it('begin=0, only debit', () => {
    expect(calcAssetEndBalance(0, 50000, 0)).toBe(50000)
  })

  it('begin=0, only credit → negative (过渡科目允许)', () => {
    expect(calcAssetEndBalance(0, 0, 30000)).toBe(-30000)
  })

  it('equal debit and credit → end = begin', () => {
    expect(calcAssetEndBalance(80000, 10000, 10000)).toBe(80000)
  })

  it('credit exceeds begin + debit → negative', () => {
    expect(calcAssetEndBalance(100, 50, 200)).toBe(-50)
  })

  it('precision boundary: 0.1 + 0.2 - 0.3 ≈ 0', () => {
    expect(calcAssetEndBalance(0.1, 0.2, 0.3)).toBeCloseTo(0, 10)
  })
})

// --- calcTriangleReconciliation: 差额 = 期末 - (期初 + 增加 - 减少) ---
describe('calcTriangleReconciliation', () => {
  it('balanced: diff = 0', () => {
    // 期末 = 期初 + 增加 - 减少 → 100 = 80 + 30 - 10
    expect(calcTriangleReconciliation(80, 30, 10, 100)).toBe(0)
  })

  it('unbalanced: positive diff (期末偏高)', () => {
    // 期末120 vs 期初80+增30-减10=100 → diff=20
    expect(calcTriangleReconciliation(80, 30, 10, 120)).toBe(20)
  })

  it('unbalanced: negative diff (期末偏低)', () => {
    // 期末90 vs 期初80+增30-减10=100 → diff=-10
    expect(calcTriangleReconciliation(80, 30, 10, 90)).toBe(-10)
  })

  it('all zeros → 0', () => {
    expect(calcTriangleReconciliation(0, 0, 0, 0)).toBe(0)
  })

  it('no movements: end = begin → balanced', () => {
    expect(calcTriangleReconciliation(50000, 0, 0, 50000)).toBe(0)
  })
})

// --- calcSubtotal: 数组求和 ---
describe('calcSubtotal', () => {
  it('normal array: [1000, 2000, 3000] = 6000', () => {
    expect(calcSubtotal([1000, 2000, 3000])).toBe(6000)
  })

  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('mixed positive and negative', () => {
    expect(calcSubtotal([5000, -2000, 3000, -1000])).toBe(5000)
  })

  it('all negative', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('large array (1~100 sum = 5050)', () => {
    const arr = Array.from({ length: 100 }, (_, i) => i + 1)
    expect(calcSubtotal(arr)).toBe(5050)
  })
})

// --- calcChangeRate: 变动率 = (本期 - 上期) / |上期| × 100 ---
describe('calcChangeRate', () => {
  it('normal growth: 120 vs 100 → 20%', () => {
    expect(calcChangeRate(120, 100)).toBe(20)
  })

  it('normal decrease: 80 vs 100 → -20%', () => {
    expect(calcChangeRate(80, 100)).toBe(-20)
  })

  it('prior = 0 → null (避免除以零)', () => {
    expect(calcChangeRate(100, 0)).toBeNull()
  })

  it('zero change: 100 vs 100 → 0%', () => {
    expect(calcChangeRate(100, 100)).toBe(0)
  })

  it('negative prior: -100 → uses abs → growth from -100 to -50 is 50%', () => {
    // ((-50) - (-100)) / |-100| × 100 = 50/100 × 100 = 50
    expect(calcChangeRate(-50, -100)).toBe(50)
  })

  it('both zero: current=0, prior=0 → null', () => {
    expect(calcChangeRate(0, 0)).toBeNull()
  })
})

// ============================================================
// useK2AmortizationEngine
// ============================================================

// --- calcStraightLineAmort: 直线法 = cost / totalPeriods × currentPeriods ---
describe('calcStraightLineAmort', () => {
  it('normal: 100000 / 12 × 3 = 25000', () => {
    expect(calcStraightLineAmort(100000, 12, 3)).toBeCloseTo(25000, 5)
  })

  it('totalPeriods = 0 → 0 (兜底)', () => {
    expect(calcStraightLineAmort(100000, 0, 3)).toBe(0)
  })

  it('cost = 0 → 0', () => {
    expect(calcStraightLineAmort(0, 12, 3)).toBe(0)
  })

  it('currentPeriods = 0 → 0 (本期不摊)', () => {
    expect(calcStraightLineAmort(100000, 12, 0)).toBe(0)
  })

  it('full period: 100000 / 12 × 12 = 100000', () => {
    expect(calcStraightLineAmort(100000, 12, 12)).toBeCloseTo(100000, 5)
  })

  it('single period: 60000 / 6 × 1 = 10000', () => {
    expect(calcStraightLineAmort(60000, 6, 1)).toBeCloseTo(10000, 5)
  })

  it('fractional result: 100000 / 7 × 2', () => {
    const expected = (100000 / 7) * 2
    expect(calcStraightLineAmort(100000, 7, 2)).toBeCloseTo(expected, 5)
  })
})

// --- calcProgressAmort: 进度法 = cost × (currentProgress - priorProgress) ---
describe('calcProgressAmort', () => {
  it('normal: 100000 × (0.6 - 0.3) = 30000', () => {
    expect(calcProgressAmort(100000, 0.6, 0.3)).toBeCloseTo(30000, 5)
  })

  it('regression (进度回退) → 0', () => {
    // currentProgress < priorProgress → 兜底返回0
    expect(calcProgressAmort(100000, 0.3, 0.6)).toBe(0)
  })

  it('both = 0 → 0', () => {
    expect(calcProgressAmort(100000, 0, 0)).toBe(0)
  })

  it('cost = 0 → 0', () => {
    expect(calcProgressAmort(0, 0.8, 0.2)).toBe(0)
  })

  it('full progress in one period: 0→1', () => {
    expect(calcProgressAmort(50000, 1.0, 0)).toBeCloseTo(50000, 5)
  })

  it('equal progress (no change) → 0', () => {
    expect(calcProgressAmort(100000, 0.5, 0.5)).toBe(0)
  })

  it('small increment: 100000 × (0.31 - 0.30) = 1000', () => {
    expect(calcProgressAmort(100000, 0.31, 0.30)).toBeCloseTo(1000, 5)
  })
})

// --- calcAmortizedBalance: 摊余成本 = cost - accumulated ---
describe('calcAmortizedBalance', () => {
  it('normal: 100000 - 30000 = 70000', () => {
    expect(calcAmortizedBalance(100000, 30000)).toBe(70000)
  })

  it('fully amortized: 100000 - 100000 = 0', () => {
    expect(calcAmortizedBalance(100000, 100000)).toBe(0)
  })

  it('no amortization yet: cost - 0 = cost', () => {
    expect(calcAmortizedBalance(50000, 0)).toBe(50000)
  })

  it('over-amortized (超摊) → negative', () => {
    // 实务中不应出现，但公式应正确计算
    expect(calcAmortizedBalance(80000, 90000)).toBe(-10000)
  })

  it('both zero → 0', () => {
    expect(calcAmortizedBalance(0, 0)).toBe(0)
  })
})

// --- calcAmortVariance: 差异 = calculated - booked ---
describe('calcAmortVariance', () => {
  it('positive variance (企业少摊): 30000 - 25000 = 5000', () => {
    expect(calcAmortVariance(30000, 25000)).toBe(5000)
  })

  it('negative variance (企业多摊): 20000 - 25000 = -5000', () => {
    expect(calcAmortVariance(20000, 25000)).toBe(-5000)
  })

  it('zero variance (一致): 25000 - 25000 = 0', () => {
    expect(calcAmortVariance(25000, 25000)).toBe(0)
  })

  it('both zero → 0', () => {
    expect(calcAmortVariance(0, 0)).toBe(0)
  })

  it('large variance', () => {
    expect(calcAmortVariance(1_000_000, 500_000)).toBe(500_000)
  })
})
