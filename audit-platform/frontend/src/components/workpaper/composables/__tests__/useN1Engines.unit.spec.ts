/**
 * Unit Tests — N1 递延所得税资产公式引擎 + 递延税引擎 + 可弥补亏损引擎
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 7.1
 *
 * 已知值验证 + 边界测试，互补 PBT 测试（n1-pbt.spec.ts）。
 * 覆盖 Properties P1~P7 的具体场景与边界情况。
 *
 * 科目：1811 递延所得税资产（借方/资产类）
 * 核心方向：期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
  calcProportion,
  calcChangeProportion,
  parseNum,
} from '../useN1FormulaEngine'
import {
  calcTemporaryDifference,
  calcDeferredTax,
  calcDeductibleDiff,
  calcTaxableDiff,
  calcDeferredTaxAsset,
  calcDeferredTaxLiability,
  calcDeferredTaxDiff,
  calcWeightedAvgRate,
} from '../useN1DeferredTaxEngine'
import {
  calcUnrecoveredLoss,
  calcRecognizableAsset,
  isCompensationExpired,
  calcRemainingYears,
} from '../useN1LossCompensationEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// useN1FormulaEngine — 资产类公式引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN1FormulaEngine', () => {
  // ── parseNum ────────────────────────────────────────────────────────────

  describe('parseNum', () => {
    it('正常数字直接返回', () => {
      expect(parseNum(100)).toBe(100)
      expect(parseNum(-50.5)).toBe(-50.5)
    })

    it('null/undefined/空字符串 → 0', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
    })

    it('NaN/Infinity → 0', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })

    it('字符串数字正常解析', () => {
      expect(parseNum('123.45')).toBe(123.45)
      expect(parseNum('-99')).toBe(-99)
    })
  })

  // ── calcAuditedAmount (P1) ──────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('已知值: 50000 + 3000 + (-1000) = 52000', () => {
      expect(calcAuditedAmount(50000, 3000, -1000)).toBe(52000)
    })

    it('全零: 0 + 0 + 0 = 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负数场景: -100 + (-200) + (-300) = -600', () => {
      expect(calcAuditedAmount(-100, -200, -300)).toBe(-600)
    })

    it('大数: 1e8 + 5e7 + 2e7 = 1.7e8', () => {
      expect(calcAuditedAmount(1e8, 5e7, 2e7)).toBe(1.7e8)
    })
  })

  // ── calcAssetEndBalance (P2) — 资产类方向！────────────────────────────────

  describe('calcAssetEndBalance — 资产类(期初+借-贷)', () => {
    it('标准场景: 10000 + 5000 - 3000 = 12000', () => {
      expect(calcAssetEndBalance(10000, 5000, 3000)).toBe(12000)
    })

    it('全零: 0 + 0 - 0 = 0', () => {
      expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
    })

    it('贷方大于期初+借方(减值) → 可为负: 1000 + 200 - 1500 = -300', () => {
      expect(calcAssetEndBalance(1000, 200, 1500)).toBe(-300)
    })

    it('仅借方增加: 5000 + 3000 - 0 = 8000', () => {
      expect(calcAssetEndBalance(5000, 3000, 0)).toBe(8000)
    })

    it('仅贷方转回: 8000 + 0 - 2000 = 6000', () => {
      expect(calcAssetEndBalance(8000, 0, 2000)).toBe(6000)
    })

    it('大数: 1e9 + 5e8 - 3e8 = 1.2e9', () => {
      expect(calcAssetEndBalance(1e9, 5e8, 3e8)).toBe(1.2e9)
    })
  })

  // ── calcSubtotal (P5) ──────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('已知值: [100, 200, 300, 400] = 1000', () => {
      expect(calcSubtotal([100, 200, 300, 400])).toBe(1000)
    })

    it('空数组: [] = 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('含负数: [500, -200, 300, -100] = 500', () => {
      expect(calcSubtotal([500, -200, 300, -100])).toBe(500)
    })

    it('单元素: [12345] = 12345', () => {
      expect(calcSubtotal([12345])).toBe(12345)
    })

    it('非数组输入 → 0', () => {
      expect(calcSubtotal(null as any)).toBe(0)
      expect(calcSubtotal(undefined as any)).toBe(0)
    })
  })

  // ── calcProportion ────────────────────────────────────────────────────

  describe('calcProportion', () => {
    it('标准: 250 / 1000 = 0.25', () => {
      expect(calcProportion(250, 1000)).toBe(0.25)
    })

    it('除零保护: total=0 → 0', () => {
      expect(calcProportion(100, 0)).toBe(0)
    })

    it('item=0 → 0', () => {
      expect(calcProportion(0, 1000)).toBe(0)
    })

    it('占比>1: 1500 / 1000 = 1.5', () => {
      expect(calcProportion(1500, 1000)).toBe(1.5)
    })
  })

  // ── calcChangeProportion ──────────────────────────────────────────────

  describe('calcChangeProportion', () => {
    it('标准变动: 200 / 1000 = 0.2', () => {
      expect(calcChangeProportion(200, 1000)).toBe(0.2)
    })

    it('base=0, change=0 → 0', () => {
      expect(calcChangeProportion(0, 0)).toBe(0)
    })

    it('base=0, change>0 → 1', () => {
      expect(calcChangeProportion(500, 0)).toBe(1)
    })

    it('base=0, change<0 → -1', () => {
      expect(calcChangeProportion(-500, 0)).toBe(-1)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useN1DeferredTaxEngine — 递延所得税测算引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN1DeferredTaxEngine', () => {
  // ── calcTemporaryDifference (P3) ────────────────────────────────────────

  describe('calcTemporaryDifference', () => {
    it('可抵扣差异(账面<计税): 800 - 1000 = -200', () => {
      expect(calcTemporaryDifference(800, 1000)).toBe(-200)
    })

    it('应纳税差异(账面>计税): 1500 - 1000 = 500', () => {
      expect(calcTemporaryDifference(1500, 1000)).toBe(500)
    })

    it('无差异: 1000 - 1000 = 0', () => {
      expect(calcTemporaryDifference(1000, 1000)).toBe(0)
    })

    it('零值: 0 - 0 = 0', () => {
      expect(calcTemporaryDifference(0, 0)).toBe(0)
    })

    it('大数: 1e9 - 5e8 = 5e8', () => {
      expect(calcTemporaryDifference(1e9, 5e8)).toBe(5e8)
    })
  })

  // ── calcDeferredTax (P4) ────────────────────────────────────────────────

  describe('calcDeferredTax', () => {
    it('标准25%: 1000000 × 0.25 = 250000', () => {
      expect(calcDeferredTax(1000000, 0.25)).toBe(250000)
    })

    it('15%优惠税率: 1000000 × 0.15 = 150000', () => {
      expect(calcDeferredTax(1000000, 0.15)).toBe(150000)
    })

    it('税率0%: 1000000 × 0 = 0', () => {
      expect(calcDeferredTax(1000000, 0)).toBe(0)
    })

    it('差异为0: 0 × 0.25 = 0', () => {
      expect(calcDeferredTax(0, 0.25)).toBe(0)
    })

    it('负差异: -500000 × 0.25 = -125000', () => {
      expect(calcDeferredTax(-500000, 0.25)).toBe(-125000)
    })

    it('大数: 1e9 × 0.25 = 2.5e8', () => {
      expect(calcDeferredTax(1e9, 0.25)).toBe(2.5e8)
    })
  })

  // ── calcDeductibleDiff ────────────────────────────────────────────────

  describe('calcDeductibleDiff', () => {
    it('可抵扣(账面<计税): 800 vs 1000 → 200', () => {
      expect(calcDeductibleDiff(800, 1000)).toBe(200)
    })

    it('应纳税(账面>计税): 1500 vs 1000 → 0', () => {
      expect(calcDeductibleDiff(1500, 1000)).toBe(0)
    })

    it('无差异: 1000 vs 1000 → 0', () => {
      expect(calcDeductibleDiff(1000, 1000)).toBe(0)
    })
  })

  // ── calcTaxableDiff ───────────────────────────────────────────────────

  describe('calcTaxableDiff', () => {
    it('应纳税(账面>计税): 1500 vs 1000 → 500', () => {
      expect(calcTaxableDiff(1500, 1000)).toBe(500)
    })

    it('可抵扣(账面<计税): 800 vs 1000 → 0', () => {
      expect(calcTaxableDiff(800, 1000)).toBe(0)
    })

    it('无差异: 1000 vs 1000 → 0', () => {
      expect(calcTaxableDiff(1000, 1000)).toBe(0)
    })
  })

  // ── calcDeferredTaxAsset ──────────────────────────────────────────────

  describe('calcDeferredTaxAsset', () => {
    it('标准: 200 × 0.25 = 50', () => {
      expect(calcDeferredTaxAsset(200, 0.25)).toBe(50)
    })

    it('零值保护: 0 × 0.25 = 0', () => {
      expect(calcDeferredTaxAsset(0, 0.25)).toBe(0)
    })

    it('15%税率: 1000 × 0.15 = 150', () => {
      expect(calcDeferredTaxAsset(1000, 0.15)).toBe(150)
    })
  })

  // ── calcDeferredTaxLiability ──────────────────────────────────────────

  describe('calcDeferredTaxLiability', () => {
    it('标准: 500 × 0.25 = 125', () => {
      expect(calcDeferredTaxLiability(500, 0.25)).toBe(125)
    })

    it('零值保护: 0 × 0.25 = 0', () => {
      expect(calcDeferredTaxLiability(0, 0.25)).toBe(0)
    })
  })

  // ── calcDeferredTaxDiff ───────────────────────────────────────────────

  describe('calcDeferredTaxDiff', () => {
    it('应追加确认: 300 - 200 = 100', () => {
      expect(calcDeferredTaxDiff(300, 200)).toBe(100)
    })

    it('应转回: 100 - 200 = -100', () => {
      expect(calcDeferredTaxDiff(100, 200)).toBe(-100)
    })

    it('无差异: 250 - 250 = 0', () => {
      expect(calcDeferredTaxDiff(250, 250)).toBe(0)
    })
  })

  // ── calcWeightedAvgRate ───────────────────────────────────────────────

  describe('calcWeightedAvgRate', () => {
    it('统一税率25%: [250, 500] / [1000, 2000] = 0.25', () => {
      expect(calcWeightedAvgRate([250, 500], [1000, 2000])).toBe(0.25)
    })

    it('混合税率: [150, 500] / [1000, 2000] ≈ 0.2167', () => {
      const result = calcWeightedAvgRate([150, 500], [1000, 2000])
      expect(result).toBeCloseTo(650 / 3000, 10)
    })

    it('除零保护: diffs全0 → 0', () => {
      expect(calcWeightedAvgRate([100, 200], [0, 0])).toBe(0)
    })

    it('空数组: [] / [] → 0', () => {
      expect(calcWeightedAvgRate([], [])).toBe(0)
    })

    it('非数组输入 → 0', () => {
      expect(calcWeightedAvgRate(null as any, null as any)).toBe(0)
    })

    it('大数: [25000000, 50000000] / [100000000, 200000000] = 0.25', () => {
      expect(calcWeightedAvgRate([25000000, 50000000], [100000000, 200000000])).toBe(0.25)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useN1LossCompensationEngine — 可弥补亏损确认引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN1LossCompensationEngine', () => {
  // ── calcUnrecoveredLoss (P6) ────────────────────────────────────────────

  describe('calcUnrecoveredLoss', () => {
    it('标准: 1000000 - 300000 = 700000', () => {
      expect(calcUnrecoveredLoss(1000000, 300000)).toBe(700000)
    })

    it('已全部弥补: 500000 - 500000 = 0', () => {
      expect(calcUnrecoveredLoss(500000, 500000)).toBe(0)
    })

    it('已弥补超过亏损(不允许负) → 0', () => {
      expect(calcUnrecoveredLoss(300000, 500000)).toBe(0)
    })

    it('全零: 0 - 0 = 0', () => {
      expect(calcUnrecoveredLoss(0, 0)).toBe(0)
    })

    it('负数输入clamp到0: (-100) treated as 0', () => {
      expect(calcUnrecoveredLoss(-100, 0)).toBe(0)
    })

    it('大数: 1e9 - 3e8 = 7e8', () => {
      expect(calcUnrecoveredLoss(1e9, 3e8)).toBe(7e8)
    })
  })

  // ── calcRecognizableAsset (P7) ──────────────────────────────────────────

  describe('calcRecognizableAsset — 谨慎性限额', () => {
    it('未来所得额充足: min(700000, 1000000) × 0.25 = 175000', () => {
      expect(calcRecognizableAsset(700000, 1000000, 0.25)).toBe(175000)
    })

    it('未来所得额不足(限额): min(700000, 400000) × 0.25 = 100000', () => {
      expect(calcRecognizableAsset(700000, 400000, 0.25)).toBe(100000)
    })

    it('未弥补亏损=0 → 0', () => {
      expect(calcRecognizableAsset(0, 1000000, 0.25)).toBe(0)
    })

    it('未来所得额=0 → 0', () => {
      expect(calcRecognizableAsset(700000, 0, 0.25)).toBe(0)
    })

    it('税率=0 → 0', () => {
      expect(calcRecognizableAsset(700000, 1000000, 0)).toBe(0)
    })

    it('15%优惠税率: min(500000, 800000) × 0.15 = 75000', () => {
      expect(calcRecognizableAsset(500000, 800000, 0.15)).toBe(75000)
    })

    it('税率>1 → 0(无效税率不确认)', () => {
      expect(calcRecognizableAsset(700000, 1000000, 1.5)).toBe(0)
    })

    it('负数unrecovered → 0', () => {
      expect(calcRecognizableAsset(-100, 1000000, 0.25)).toBe(0)
    })
  })

  // ── isCompensationExpired ─────────────────────────────────────────────

  describe('isCompensationExpired', () => {
    // 一般企业5年弥补期限
    it('5年未到期: lossYear=2021, current=2025, max=5 → false', () => {
      expect(isCompensationExpired(2021, 2025, 5)).toBe(false)
    })

    it('5年边界(最后一年): lossYear=2020, current=2025, max=5 → false', () => {
      expect(isCompensationExpired(2020, 2025, 5)).toBe(false)
    })

    it('5年刚好届满: lossYear=2020, current=2026, max=5 → true', () => {
      expect(isCompensationExpired(2020, 2026, 5)).toBe(true)
    })

    it('5年已超过: lossYear=2018, current=2025, max=5 → true', () => {
      expect(isCompensationExpired(2018, 2025, 5)).toBe(true)
    })

    // 高新/科技型中小企业10年弥补期限
    it('10年未到期: lossYear=2018, current=2025, max=10 → false', () => {
      expect(isCompensationExpired(2018, 2025, 10)).toBe(false)
    })

    it('10年边界(最后一年): lossYear=2015, current=2025, max=10 → false', () => {
      expect(isCompensationExpired(2015, 2025, 10)).toBe(false)
    })

    it('10年刚好届满: lossYear=2015, current=2026, max=10 → true', () => {
      expect(isCompensationExpired(2015, 2026, 10)).toBe(true)
    })

    // 边界/无效输入
    it('无效年份(0) → true', () => {
      expect(isCompensationExpired(0, 2025, 5)).toBe(true)
    })

    it('无效年限(0) → true', () => {
      expect(isCompensationExpired(2020, 2025, 0)).toBe(true)
    })
  })

  // ── calcRemainingYears ────────────────────────────────────────────────

  describe('calcRemainingYears', () => {
    it('标准: 2021 + 5 - 2025 = 1', () => {
      expect(calcRemainingYears(2021, 2025, 5)).toBe(1)
    })

    it('边界(最后一年): 2020 + 5 - 2025 = 0', () => {
      expect(calcRemainingYears(2020, 2025, 5)).toBe(0)
    })

    it('已过期不返负: 2018 + 5 - 2025 → 0', () => {
      expect(calcRemainingYears(2018, 2025, 5)).toBe(0)
    })

    it('10年剩余: 2020 + 10 - 2025 = 5', () => {
      expect(calcRemainingYears(2020, 2025, 10)).toBe(5)
    })

    it('无效输入 → 0', () => {
      expect(calcRemainingYears(0, 2025, 5)).toBe(0)
    })
  })
})
