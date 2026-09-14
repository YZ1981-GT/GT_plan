/**
 * Unit Tests — H6 固定资产清理公式引擎（边界/边缘情况）
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/ Task 7.1
 * Requirements: P1-P5
 *
 * 与 h6FormulaEngine.pbt.spec.ts 互补：
 * - PBT 验证公式在随机输入下的数学正确性
 * - 本文件验证特定边界情况和边缘条件
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcNetBookValue,
  calcDisposalGainLoss,
  calcSubtotal,
  isTransitBalanceZero,
  isClearingOverOneYear,
} from '../composables/useH6FormulaEngine'

// ============================================================
// calcAuditedAmount — 审定数 = 未审数 + AJE + RJE
// ============================================================
describe('calcAuditedAmount — edge cases', () => {
  it('all zero inputs → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('negative AJE (调减)', () => {
    expect(calcAuditedAmount(1000, -200, 0)).toBe(800)
  })

  it('negative RJE (重分类调出)', () => {
    expect(calcAuditedAmount(500, 0, -500)).toBe(0)
  })

  it('both AJE and RJE negative', () => {
    expect(calcAuditedAmount(1000, -300, -200)).toBe(500)
  })

  it('large numbers (亿级)', () => {
    const unadj = 1_000_000_000
    const aje = 500_000_000
    const rje = -200_000_000
    expect(calcAuditedAmount(unadj, aje, rje)).toBe(1_300_000_000)
  })

  it('fractional amounts (分级精度)', () => {
    expect(calcAuditedAmount(100.01, 0.99, 0)).toBeCloseTo(101, 5)
  })
})

// ============================================================
// calcAssetEndBalance — 资产类期末余额 = 期初 + 借方 - 贷方
// ============================================================
describe('calcAssetEndBalance — edge cases', () => {
  it('all zero → 0', () => {
    expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
  })

  it('zero begin balance, only debit', () => {
    expect(calcAssetEndBalance(0, 5000, 0)).toBe(5000)
  })

  it('credit exceeds begin + debit → negative end balance', () => {
    // 贷方 > 期初+借方 → 负余额（过渡科目可能出现）
    expect(calcAssetEndBalance(100, 50, 200)).toBe(-50)
  })

  it('equal debit and credit → end = begin', () => {
    expect(calcAssetEndBalance(1000, 500, 500)).toBe(1000)
  })

  it('large begin balance with zero movements', () => {
    expect(calcAssetEndBalance(999_999_999, 0, 0)).toBe(999_999_999)
  })

  it('precision boundary', () => {
    expect(calcAssetEndBalance(0.1, 0.2, 0.3)).toBeCloseTo(0, 10)
  })
})

// ============================================================
// calcNetBookValue — 净账面价值 = 原值 - 累计折旧
// ============================================================
describe('calcNetBookValue — edge cases', () => {
  it('zero cost and zero depreciation → 0', () => {
    expect(calcNetBookValue(0, 0)).toBe(0)
  })

  it('over-depreciated (累计折旧 > 原值) → negative', () => {
    // 实务中不应发生，但公式应正确计算
    expect(calcNetBookValue(100, 150)).toBe(-50)
  })

  it('fully depreciated → 0', () => {
    expect(calcNetBookValue(50000, 50000)).toBe(0)
  })

  it('no depreciation → equals cost', () => {
    expect(calcNetBookValue(120000, 0)).toBe(120000)
  })

  it('large asset value', () => {
    expect(calcNetBookValue(500_000_000, 125_000_000)).toBe(375_000_000)
  })
  it('with impairment provision → cost - dep - impair', () => {
    expect(calcNetBookValue(100000, 30000, 10000)).toBe(60000)
  })

  it('impairment defaults to 0 (两参数兼容)', () => {
    expect(calcNetBookValue(100000, 30000)).toBe(70000)
  })
})

// ============================================================
// isClearingOverOneYear — 超1年挂账判定
// ============================================================
describe('isClearingOverOneYear — edge cases', () => {
  it('empty startDate → false', () => {
    expect(isClearingOverOneYear('', '2025-12-31')).toBe(false)
  })

  it('within one year → false', () => {
    expect(isClearingOverOneYear('2025-01-01', '2025-12-31')).toBe(false)
  })

  it('exactly one year → true', () => {
    expect(isClearingOverOneYear('2024-12-31', '2025-12-31')).toBe(true)
  })

  it('over one year → true', () => {
    expect(isClearingOverOneYear('2023-06-01', '2025-12-31')).toBe(true)
  })
})

// ============================================================
describe('calcDisposalGainLoss — edge cases', () => {
  it('all zero → 0 (无实质清理)', () => {
    expect(calcDisposalGainLoss(0, 0, 0, 0)).toBe(0)
  })

  it('net loss scenario (收入 < 净值+费用+税)', () => {
    // 处置收入50万 < 净值80万+费用5万+税2万 → 净亏损37万
    expect(calcDisposalGainLoss(500000, 800000, 50000, 20000)).toBe(-370000)
  })

  it('net gain scenario (收入 > 净值+费用+税)', () => {
    expect(calcDisposalGainLoss(1000000, 300000, 50000, 100000)).toBe(550000)
  })

  it('breakeven (收入刚好等于支出)', () => {
    expect(calcDisposalGainLoss(100, 60, 30, 10)).toBe(0)
  })

  it('zero income with costs (报废无收入)', () => {
    expect(calcDisposalGainLoss(0, 200000, 5000, 0)).toBe(-205000)
  })

  it('zero net value (已提足折旧)', () => {
    expect(calcDisposalGainLoss(10000, 0, 1000, 500)).toBe(8500)
  })
})

// ============================================================
// calcSubtotal — 合计数组求和
// ============================================================
describe('calcSubtotal — edge cases', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('negative elements', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('mixed positive and negative', () => {
    expect(calcSubtotal([1000, -500, 200, -100])).toBe(600)
  })

  it('large array', () => {
    const arr = Array.from({ length: 100 }, (_, i) => i + 1) // 1~100
    expect(calcSubtotal(arr)).toBe(5050)
  })

  it('single zero element', () => {
    expect(calcSubtotal([0])).toBe(0)
  })
})

// ============================================================
// isTransitBalanceZero — 过渡科目零余额判定
// ============================================================
describe('isTransitBalanceZero — edge cases', () => {
  it('exactly 0 → true', () => {
    expect(isTransitBalanceZero(0)).toBe(true)
  })

  it('positive 0 → true', () => {
    expect(isTransitBalanceZero(+0)).toBe(true)
  })

  it('negative 0 → true', () => {
    expect(isTransitBalanceZero(-0)).toBe(true)
  })

  it('small positive (e.g. 0.01) → false', () => {
    expect(isTransitBalanceZero(0.01)).toBe(false)
  })

  it('small negative (e.g. -0.01) → false', () => {
    expect(isTransitBalanceZero(-0.01)).toBe(false)
  })

  it('large positive → false', () => {
    expect(isTransitBalanceZero(999_999_999)).toBe(false)
  })

  it('large negative → false', () => {
    expect(isTransitBalanceZero(-999_999_999)).toBe(false)
  })

  it('NaN → false', () => {
    expect(isTransitBalanceZero(NaN)).toBe(false)
  })
})
