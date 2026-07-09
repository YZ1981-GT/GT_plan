/**
 * I4 长期待摊费用 — 公式引擎 + 摊销引擎 确定性边界测试
 * 覆盖 useI4FormulaEngine + useI4AmortizationEngine 所有纯函数
 * Spec: .kiro/specs/i4-long-term-prepaid/ Task 7.1
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from '../composables/useI4FormulaEngine'
import {
  calcStraightLineAmort,
  calcUnitsOfProductionAmort,
  calcRemainingMonths,
  calcAmortizationRate,
} from '../composables/useI4AmortizationEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// useI4FormulaEngine
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAuditedAmount', () => {
  it('正常值：100 + 20 + 10 = 130', () => {
    expect(calcAuditedAmount(100, 20, 10)).toBe(130)
  })

  it('全零：0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数 AJE/RJE：1000 + (-50) + (-30) = 920', () => {
    expect(calcAuditedAmount(1000, -50, -30)).toBe(920)
  })
})

describe('calcAssetEndBalance', () => {
  it('基本用例：1000 + 200 - 100 - 50 = 1050', () => {
    expect(calcAssetEndBalance(1000, 200, 100, 50)).toBe(1050)
  })

  it('零摊销：500 + 100 - 0 - 0 = 600', () => {
    expect(calcAssetEndBalance(500, 100, 0, 0)).toBe(600)
  })

  it('负结果(超摊)：100 + 0 - 200 - 0 = -100', () => {
    expect(calcAssetEndBalance(100, 0, 200, 0)).toBe(-100)
  })
})

describe('calcTriangleReconciliation', () => {
  it('平衡：差额=0', () => {
    // end == begin + increase - amort - decrease
    expect(calcTriangleReconciliation(1000, 200, 100, 50, 1050)).toBe(0)
  })

  it('不平衡：差额≠0', () => {
    // expected end = 1000 + 200 - 100 - 50 = 1050，实际给1060 → diff=10
    expect(calcTriangleReconciliation(1000, 200, 100, 50, 1060)).toBe(10)
  })
})

describe('calcSubtotal', () => {
  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('多元素', () => {
    expect(calcSubtotal([10, 20, 30, 40])).toBe(100)
  })
})

describe('calcChangeRate', () => {
  it('正常变动率：(120-100)/100 = 0.2', () => {
    expect(calcChangeRate(120, 100)).toBeCloseTo(0.2)
  })

  it('前期为0返回null', () => {
    expect(calcChangeRate(100, 0)).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useI4AmortizationEngine
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcStraightLineAmort', () => {
  it('正常用例：120000 / 24 = 5000', () => {
    expect(calcStraightLineAmort(120000, 24)).toBe(5000)
  })

  it('totalMonths=0 返回 0', () => {
    expect(calcStraightLineAmort(100000, 0)).toBe(0)
  })
})

describe('calcUnitsOfProductionAmort', () => {
  it('正常用例：100000 × (500/10000) = 5000', () => {
    expect(calcUnitsOfProductionAmort(100000, 500, 10000)).toBe(5000)
  })

  it('totalUnits=0 返回 0', () => {
    expect(calcUnitsOfProductionAmort(100000, 500, 0)).toBe(0)
  })
})

describe('calcRemainingMonths', () => {
  it('正值结果：36 - 12 = 24', () => {
    expect(calcRemainingMonths(36, 12)).toBe(24)
  })

  it('负值结果(超期)：24 - 30 = -6', () => {
    expect(calcRemainingMonths(24, 30)).toBe(-6)
  })
})

describe('calcAmortizationRate', () => {
  it('正常进度：12/36 ≈ 0.333', () => {
    expect(calcAmortizationRate(12, 36)).toBeCloseTo(1 / 3)
  })

  it('total=0 返回 0', () => {
    expect(calcAmortizationRate(10, 0)).toBe(0)
  })
})
