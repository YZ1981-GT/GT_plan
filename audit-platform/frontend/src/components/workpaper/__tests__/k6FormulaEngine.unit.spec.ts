/**
 * Unit Tests — K6 持有待售资产和负债公式引擎（边界/边缘情况）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 2.1
 * Requirements: 2.3-2.4, 3.2, 9.1-9.2, 9.7
 *
 * 科目：持有待售资产（**借方/资产类**）+ 持有待售负债（**贷方/负债类**）
 * ⚠️ 混合科目！资产类期末=期初+增加-减少-减值；负债类期末=期初+增加-减少
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcBookValue,
  calcSubtotal,
  calcAssetPeriodEnd,
  calcLiabilityPeriodEnd,
  calcVariationRate,
} from '../composables/useK6FormulaEngine'

// ============================================================
// calcAuditedAmount — 审定数 = 未审 + AJE + RJE (Req 9.1)
// ============================================================
describe('calcAuditedAmount — 审定数公式 (Req 9.1)', () => {
  it('all zero inputs → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('standard case: 1000 + 200 + 50 = 1250', () => {
    expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
  })

  it('negative AJE (审计调减)', () => {
    expect(calcAuditedAmount(1000, -200, 0)).toBe(800)
  })

  it('negative RJE (重分类调出)', () => {
    expect(calcAuditedAmount(500, 0, -500)).toBe(0)
  })

  it('both AJE and RJE negative', () => {
    expect(calcAuditedAmount(1000, -300, -200)).toBe(500)
  })

  it('large numbers (1e12 万亿级)', () => {
    expect(calcAuditedAmount(1e12, 5e11, -2e11)).toBe(1.3e12)
  })

  it('fractional amounts (分级精度)', () => {
    expect(calcAuditedAmount(100.01, 0.99, 0)).toBeCloseTo(101, 5)
  })

  it('NaN input treated as 0', () => {
    expect(calcAuditedAmount(NaN, 10, 20)).toBe(30)
    expect(calcAuditedAmount(100, NaN, NaN)).toBe(100)
  })

  it('undefined input treated as 0', () => {
    expect(calcAuditedAmount(undefined as any, 50, 50)).toBe(100)
  })

  it('Infinity input treated as 0', () => {
    expect(calcAuditedAmount(Infinity, 10, 20)).toBe(30)
    expect(calcAuditedAmount(100, -Infinity, 0)).toBe(100)
  })
})

// ============================================================
// calcBookValue — 账面价值 = 原值 - 折旧摊销 - 减值 (Req 9.2, 3.2)
// ============================================================
describe('calcBookValue — 账面价值公式 (Req 9.2, 3.2)', () => {
  it('all zero → 0', () => {
    expect(calcBookValue(0, 0, 0)).toBe(0)
  })

  it('standard case: 10000 - 3000 - 1000 = 6000', () => {
    expect(calcBookValue(10000, 3000, 1000)).toBe(6000)
  })

  it('no depreciation and no impairment → cost itself', () => {
    expect(calcBookValue(50000, 0, 0)).toBe(50000)
  })

  it('full depreciation → book value = -impairment or 0', () => {
    expect(calcBookValue(10000, 10000, 0)).toBe(0)
  })

  it('over-depreciation can produce negative (超额折旧)', () => {
    expect(calcBookValue(10000, 12000, 0)).toBe(-2000)
  })

  it('NaN inputs treated as 0', () => {
    expect(calcBookValue(NaN, 3000, 1000)).toBe(-4000)
    expect(calcBookValue(10000, NaN, NaN)).toBe(10000)
  })

  it('undefined inputs treated as 0', () => {
    expect(calcBookValue(undefined as any, 1000, 500)).toBe(-1500)
  })

  it('Infinity inputs treated as 0', () => {
    expect(calcBookValue(Infinity, 1000, 500)).toBe(-1500)
    expect(calcBookValue(10000, Infinity, 0)).toBe(10000)
  })

  it('large numbers', () => {
    expect(calcBookValue(1e9, 3e8, 1e8)).toBe(6e8)
  })
})

// ============================================================
// calcSubtotal — 合计 = Σarr (Req 9.7)
// ============================================================
describe('calcSubtotal — 合计公式 (Req 9.7)', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('null/undefined array → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('multiple elements', () => {
    expect(calcSubtotal([1000, 2000, 3000])).toBe(6000)
  })

  it('NaN elements treated as 0', () => {
    expect(calcSubtotal([NaN, 5, NaN, 10])).toBe(15)
  })

  it('Infinity elements treated as 0', () => {
    expect(calcSubtotal([Infinity, 5, -Infinity, 10])).toBe(15)
  })

  it('negative elements', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('mixed positive and negative', () => {
    expect(calcSubtotal([1000, -500, 200, -100])).toBe(600)
  })
})

// ============================================================
// calcAssetPeriodEnd — 资产类期末 = 期初 + 增加 - 减少 - 减值 (Req 2.3)
// ============================================================
describe('calcAssetPeriodEnd — 资产类期末公式 (Req 2.3)', () => {
  it('all zero → 0', () => {
    expect(calcAssetPeriodEnd(0, 0, 0, 0)).toBe(0)
  })

  it('standard case: 1000 + 500 - 200 - 100 = 1200', () => {
    expect(calcAssetPeriodEnd(1000, 500, 200, 100)).toBe(1200)
  })

  it('no change → period end = opening', () => {
    expect(calcAssetPeriodEnd(5000, 0, 0, 0)).toBe(5000)
  })

  it('only increase → end > opening', () => {
    expect(calcAssetPeriodEnd(1000, 2000, 0, 0)).toBe(3000)
  })

  it('decrease exceeds → negative balance', () => {
    expect(calcAssetPeriodEnd(100, 0, 500, 0)).toBe(-400)
  })

  it('impairment reduces end balance', () => {
    expect(calcAssetPeriodEnd(10000, 0, 0, 3000)).toBe(7000)
  })

  it('NaN inputs treated as 0', () => {
    expect(calcAssetPeriodEnd(NaN, 500, 200, 100)).toBe(200)
  })

  it('Infinity inputs treated as 0', () => {
    expect(calcAssetPeriodEnd(1000, Infinity, 200, 100)).toBe(700)
  })

  it('verify ASSET direction: begin + inc - dec - impairment', () => {
    // 资产类：期初 5000，增加 2000，减少 1000，减值 500
    //   → 期末 = 5000 + 2000 - 1000 - 500 = 5500
    expect(calcAssetPeriodEnd(5000, 2000, 1000, 500)).toBe(5500)
  })
})

// ============================================================
// calcLiabilityPeriodEnd — 负债类期末 = 期初 + 增加 - 减少 (Req 2.4 负债区块)
// ============================================================
describe('calcLiabilityPeriodEnd — 负债类期末公式 (Req 2.4)', () => {
  it('all zero → 0', () => {
    expect(calcLiabilityPeriodEnd(0, 0, 0)).toBe(0)
  })

  it('standard case: 1000 + 500 - 200 = 1300', () => {
    expect(calcLiabilityPeriodEnd(1000, 500, 200)).toBe(1300)
  })

  it('only increase → end > opening', () => {
    expect(calcLiabilityPeriodEnd(1000, 500, 0)).toBe(1500)
  })

  it('only decrease → end < opening', () => {
    expect(calcLiabilityPeriodEnd(1000, 0, 300)).toBe(700)
  })

  it('decrease exceeds → negative balance', () => {
    expect(calcLiabilityPeriodEnd(100, 0, 200)).toBe(-100)
  })

  it('NaN inputs treated as 0', () => {
    expect(calcLiabilityPeriodEnd(NaN, 100, 50)).toBe(50)
  })

  it('Infinity inputs treated as 0', () => {
    expect(calcLiabilityPeriodEnd(Infinity, 100, 50)).toBe(50)
  })

  it('verify LIABILITY direction vs ASSET direction', () => {
    // 负债类：期初 1000，增加 500，减少 200 → 期末 = 1000 + 500 - 200 = 1300
    // 注意：负债类无减值参数，比资产类少一个减值扣除
    expect(calcLiabilityPeriodEnd(1000, 500, 200)).toBe(1300)
  })
})

// ============================================================
// calcVariationRate — 变动率 = (审定 - 上期) / 上期 (兜底除零)
// ============================================================
describe('calcVariationRate — 变动率公式', () => {
  it('prior=0, current=0 → null (无变动无意义)', () => {
    expect(calcVariationRate(0, 0)).toBeNull()
  })

  it('prior=0, current≠0 → 1 (100%增长兜底)', () => {
    expect(calcVariationRate(0, 1000)).toBe(1)
  })

  it('standard case: prior=1000, current=1200 → 0.2 (20%)', () => {
    expect(calcVariationRate(1000, 1200)).toBeCloseTo(0.2, 10)
  })

  it('decrease: prior=1000, current=800 → -0.2 (-20%)', () => {
    expect(calcVariationRate(1000, 800)).toBeCloseTo(-0.2, 10)
  })

  it('no change: prior=1000, current=1000 → 0', () => {
    expect(calcVariationRate(1000, 1000)).toBe(0)
  })

  it('100% increase: prior=500, current=1000 → 1.0', () => {
    expect(calcVariationRate(500, 1000)).toBe(1)
  })

  it('full decrease: prior=1000, current=0 → -1.0 (-100%)', () => {
    expect(calcVariationRate(1000, 0)).toBe(-1)
  })

  it('NaN prior → treated as 0, current≠0 → 1', () => {
    expect(calcVariationRate(NaN, 500)).toBe(1)
  })

  it('NaN current → treated as 0, prior≠0 → -1', () => {
    expect(calcVariationRate(1000, NaN)).toBe(-1)
  })

  it('both NaN → null', () => {
    expect(calcVariationRate(NaN, NaN)).toBeNull()
  })

  it('Infinity inputs treated as 0', () => {
    expect(calcVariationRate(Infinity, 500)).toBe(1) // prior=0, current≠0 → 1
    expect(calcVariationRate(1000, Infinity)).toBe(-1) // prior=1000, current=0 → -1
  })
})
