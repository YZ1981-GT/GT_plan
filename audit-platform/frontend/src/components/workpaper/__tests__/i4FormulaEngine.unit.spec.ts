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
  calcAmortStandard,
  calcUnitsAmortByStandard,
  calcAmortDiff,
  calcRemainingMonths,
  calcAmortizationRate,
  calcStraightLineAmortTest,
  parseUsefulLifeToMonths,
  calcFullAmortDate,
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

describe('calcAmortStandard / calcUnitsAmortByStandard / calcAmortDiff（I4-7源表）', () => {
  it('摊销标准 = 原值 ÷ 工作标准', () => {
    expect(calcAmortStandard(100000, 10000)).toBe(10)
  })

  it('工作标准=0 时摊销标准为 0', () => {
    expect(calcAmortStandard(100000, 0)).toBe(0)
  })

  it('测算本年 = 本期工作量 × 摊销标准（等价于 原值×本期量/总量）', () => {
    const std = calcAmortStandard(100000, 10000)
    expect(calcUnitsAmortByStandard(500, std)).toBe(5000)
    expect(calcUnitsAmortByStandard(500, std)).toBe(calcUnitsOfProductionAmort(100000, 500, 10000))
  })

  it('差异 = 测算 − 账面', () => {
    expect(calcAmortDiff(5000, 4800)).toBe(200)
    expect(calcAmortDiff(5000, 5200)).toBe(-200)
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

describe('calcStraightLineAmortTest（I4-6源表）', () => {
  it('解析使用年限：5年 → 60月', () => {
    expect(parseUsefulLifeToMonths('5年')).toBe(60)
    expect(parseUsefulLifeToMonths(5)).toBe(60)
  })

  it('开始日为空时不推算到期日（避免1900-1-0）', () => {
    expect(calcFullAmortDate('', 60)).toBe('')
    expect(calcFullAmortDate(null, 60)).toBe('')
  })

  it('整年在用：月摊=原值/60，本期月数=12，当期=月摊×12', () => {
    const r = calcStraightLineAmortTest({
      originalAmount: 120000,
      usefulLife: '5年',
      startDate: '2023-01-01',
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
      bookMonthlyAmort: 2000,
      bookAccumAmort: 48000,
    })
    expect(r.lifeMonths).toBe(60)
    expect(r.calcMonthlyAmort).toBeCloseTo(2000, 4)
    expect(r.periodMonths).toBe(12)
    expect(r.periodAmortization).toBeCloseTo(24000, 2)
    expect(r.monthlyDiff).toBeCloseTo(0, 2)
  })

  it('已摊完项目本期月数为0（非虚增）', () => {
    const r = calcStraightLineAmortTest({
      originalAmount: 120000,
      usefulLife: '5年',
      startDate: '2020-01-01',
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
    })
    expect(r.remainingMonths).toBe(0)
    expect(r.periodMonths).toBe(0)
    expect(r.fullAmortDate).toBeTruthy()
  })

  it('老资产本期月数不虚增（≠ DATEDIF(开始,截止)+1）', () => {
    const r = calcStraightLineAmortTest({
      originalAmount: 120000,
      usefulLife: '10年',
      startDate: '2020-01-01',
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
    })
    // 若误用 DATEDIF(2020-01,2025-12)+1 ≈ 72，会虚增；正确本期应为 12
    expect(r.periodMonths).toBe(12)
  })

  it('年内新增：本期月数按开始日到期末', () => {
    const r = calcStraightLineAmortTest({
      originalAmount: 12000,
      usefulLife: '2年',
      startDate: '2025-07-01',
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
    })
    expect(r.periodMonths).toBe(6)
    expect(r.calcMonthlyAmort).toBeCloseTo(500, 4)
    expect(r.periodAmortization).toBeCloseTo(3000, 2)
  })
})
