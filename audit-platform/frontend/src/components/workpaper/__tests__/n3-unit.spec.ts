/**
 * N3 递延所得税负债 — 单元测试：useN3FormulaEngine + useN3DeferredTaxEngine
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/ Task 7.1
 * Requirements: P1-P5
 *
 * 覆盖：
 * - calcAuditedAmount: 审定数=未审+AJE+RJE（标准/零值/负调整）
 * - calcLiabilityEndBalance: 负债类期末=期初+贷方-借方（标准/大数/全零/借方>期初+贷方）
 * - calcSubtotal: 合计行恒等（空数组/单元素/多元素/负值）
 * - calcProportion: 占比计算（正常/total=0/item=0）
 * - calcChange: 变动额（正/负/零）
 * - calcChangeRate: 变动率（正常/begin=0+change=0/begin=0+change>0/begin=0+change<0）
 * - calcTaxableTemporaryDifference: 应纳税暂时性差异（账面>计税/账面<计税/相等）
 * - calcDeferredTaxLiability: 递延税负债=差异×税率（标准/零差异/零税率）
 * - calcDeferredTaxLiabilityRounded: ROUND(diff*rate, 2) 匹配xlsx
 * - calcWeightedAvgRate: 加权平均税率（正常/空数组/全零差异）
 * - isSpecialNonRecognitionItem: 不确认递延税负债的特殊项检测
 *
 * 边界：零值/大数/税率边界/除零保护
 */
import { describe, it, expect } from 'vitest'

import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcProportion,
  calcChange,
  calcChangeRate,
} from '../composables/useN3FormulaEngine'

import {
  calcTaxableTemporaryDifference,
  calcDeferredTaxLiability,
  calcDeferredTaxLiabilityRounded,
  calcWeightedAvgRate,
  isSpecialNonRecognitionItem,
} from '../composables/useN3DeferredTaxEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// useN3FormulaEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN3FormulaEngine', () => {
  // ─── calcAuditedAmount (P1) ───────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('标准: 1000 + 50 + 30 = 1080', () => {
      expect(calcAuditedAmount(1000, 50, 30)).toBe(1080)
    })

    it('零值: 0 + 0 + 0 = 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负AJE调减: 2000 + (-100) + 0 = 1900', () => {
      expect(calcAuditedAmount(2000, -100, 0)).toBe(1900)
    })

    it('负RJE重分类: 800 + 0 + (-300) = 500', () => {
      expect(calcAuditedAmount(800, 0, -300)).toBe(500)
    })

    it('全负值: -500 + (-100) + (-50) = -650', () => {
      expect(calcAuditedAmount(-500, -100, -50)).toBe(-650)
    })

    it('大数: 1e9 + 5e7 + 2e7 = 1.07e9', () => {
      expect(calcAuditedAmount(1e9, 5e7, 2e7)).toBe(1.07e9)
    })

    it('小数精度: 100.55 + 20.33 + 10.12 ≈ 131', () => {
      expect(calcAuditedAmount(100.55, 20.33, 10.12)).toBeCloseTo(131, 2)
    })
  })

  // ─── calcLiabilityEndBalance (P2) ─────────────────────────────────────────

  describe('calcLiabilityEndBalance（负债类：期初+贷方-借方）', () => {
    it('标准: 期初5000+贷方2000-借方800 = 6200', () => {
      expect(calcLiabilityEndBalance(5000, 2000, 800)).toBe(6200)
    })

    it('全零: 0+0-0 = 0', () => {
      expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
    })

    it('大数: 1e9+5e8-2e8 = 1.3e9', () => {
      expect(calcLiabilityEndBalance(1e9, 5e8, 2e8)).toBe(1.3e9)
    })

    it('借方>期初+贷方（罕见负余额）: 100+50-300 = -150', () => {
      expect(calcLiabilityEndBalance(100, 50, 300)).toBe(-150)
    })

    it('全部转回: 5000+0-5000 = 0', () => {
      expect(calcLiabilityEndBalance(5000, 0, 5000)).toBe(0)
    })

    it('只有确认: 0+3000-0 = 3000', () => {
      expect(calcLiabilityEndBalance(0, 3000, 0)).toBe(3000)
    })

    it('方向验证：确保是期初+贷-借（非资产类期初+借-贷）', () => {
      // 负债类：期末 = 期初+贷-借 = 2000+500-100 = 2400
      // 如果错成资产类 期初+借-贷 = 2000+100-500 = 1600（错误）
      const result = calcLiabilityEndBalance(2000, 500, 100)
      expect(result).toBe(2400)
      expect(result).not.toBe(1600)
    })

    it('小数精度: 1234.56 + 789.12 - 456.78 ≈ 1566.90', () => {
      expect(calcLiabilityEndBalance(1234.56, 789.12, 456.78)).toBeCloseTo(1566.9, 2)
    })
  })

  // ─── calcSubtotal (P5) ────────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('空数组: [] = 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素: [500000] = 500000', () => {
      expect(calcSubtotal([500000])).toBe(500000)
    })

    it('多元素: [100000, 200000, 300000, 50000] = 650000', () => {
      expect(calcSubtotal([100000, 200000, 300000, 50000])).toBe(650000)
    })

    it('含负值: [500000, -100000, 300000] = 700000', () => {
      expect(calcSubtotal([500000, -100000, 300000])).toBe(700000)
    })

    it('全零: [0, 0, 0] = 0', () => {
      expect(calcSubtotal([0, 0, 0])).toBe(0)
    })

    it('大数: [1e9, 2e9, 3e9] = 6e9', () => {
      expect(calcSubtotal([1e9, 2e9, 3e9])).toBe(6e9)
    })
  })

  // ─── calcProportion ───────────────────────────────────────────────────────

  describe('calcProportion', () => {
    it('正常: 250000 / 1000000 = 0.25', () => {
      expect(calcProportion(250000, 1000000)).toBeCloseTo(0.25, 5)
    })

    it('total=0: 500000 / 0 = 0（除零保护）', () => {
      expect(calcProportion(500000, 0)).toBe(0)
    })

    it('item=0: 0 / 1000000 = 0', () => {
      expect(calcProportion(0, 1000000)).toBe(0)
    })

    it('100%: 1000000 / 1000000 = 1', () => {
      expect(calcProportion(1000000, 1000000)).toBeCloseTo(1, 5)
    })

    it('小比例: 10000 / 10000000 = 0.001', () => {
      expect(calcProportion(10000, 10000000)).toBeCloseTo(0.001, 5)
    })
  })

  // ─── calcChange ───────────────────────────────────────────────────────────

  describe('calcChange', () => {
    it('正变动（净增加）: 期末8000 - 期初5000 = 3000', () => {
      expect(calcChange(8000, 5000)).toBe(3000)
    })

    it('负变动（净减少）: 期末3000 - 期初5000 = -2000', () => {
      expect(calcChange(3000, 5000)).toBe(-2000)
    })

    it('零变动: 期末5000 - 期初5000 = 0', () => {
      expect(calcChange(5000, 5000)).toBe(0)
    })

    it('从零开始: 期末2000 - 期初0 = 2000', () => {
      expect(calcChange(2000, 0)).toBe(2000)
    })

    it('到零结束: 期末0 - 期初3000 = -3000', () => {
      expect(calcChange(0, 3000)).toBe(-3000)
    })
  })

  // ─── calcChangeRate ───────────────────────────────────────────────────────

  describe('calcChangeRate', () => {
    it('正常: begin=1000, change=200 → 0.2 (20%)', () => {
      expect(calcChangeRate(1000, 200)).toBeCloseTo(0.2, 5)
    })

    it('begin=0 且 change=0 → 0', () => {
      expect(calcChangeRate(0, 0)).toBe(0)
    })

    it('begin=0 且 change>0 → 1 (从无到有)', () => {
      expect(calcChangeRate(0, 500)).toBe(1)
    })

    it('begin=0 且 change<0 → 0（xlsx公式隐式返回0）', () => {
      expect(calcChangeRate(0, -200)).toBe(0)
    })

    it('负变动率: begin=1000, change=-300 → -0.3', () => {
      expect(calcChangeRate(1000, -300)).toBeCloseTo(-0.3, 5)
    })

    it('100%增长: begin=500, change=500 → 1.0', () => {
      expect(calcChangeRate(500, 500)).toBeCloseTo(1.0, 5)
    })

    it('大基数小变动: begin=1e9, change=1000 → 1e-6', () => {
      expect(calcChangeRate(1e9, 1000)).toBeCloseTo(1e-6, 10)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useN3DeferredTaxEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN3DeferredTaxEngine', () => {
  // ─── calcTaxableTemporaryDifference (P3) ──────────────────────────────────

  describe('calcTaxableTemporaryDifference', () => {
    it('账面>计税基础（应纳税）: 8000000 - 6000000 = 2000000', () => {
      // 固定资产折旧差异：会计余额800万，税法余额600万
      expect(calcTaxableTemporaryDifference(8000000, 6000000)).toBe(2000000)
    })

    it('账面<计税基础（可抵扣，走N1）: 5000000 - 7000000 = -2000000', () => {
      expect(calcTaxableTemporaryDifference(5000000, 7000000)).toBe(-2000000)
    })

    it('账面=计税基础（无差异）: 3000000 - 3000000 = 0', () => {
      expect(calcTaxableTemporaryDifference(3000000, 3000000)).toBe(0)
    })

    it('零值: 0 - 0 = 0', () => {
      expect(calcTaxableTemporaryDifference(0, 0)).toBe(0)
    })

    it('大数: 1e9 - 5e8 = 5e8', () => {
      expect(calcTaxableTemporaryDifference(1e9, 5e8)).toBe(5e8)
    })

    it('小数: 1234567.89 - 987654.32 ≈ 246913.57', () => {
      expect(calcTaxableTemporaryDifference(1234567.89, 987654.32)).toBeCloseTo(246913.57, 2)
    })
  })

  // ─── calcDeferredTaxLiability (P4) ────────────────────────────────────────

  describe('calcDeferredTaxLiability', () => {
    it('标准25%: 2000000 × 0.25 = 500000', () => {
      expect(calcDeferredTaxLiability(2000000, 0.25)).toBe(500000)
    })

    it('15%高新税率: 2000000 × 0.15 = 300000', () => {
      expect(calcDeferredTaxLiability(2000000, 0.15)).toBe(300000)
    })

    it('零差异: 0 × 0.25 = 0', () => {
      expect(calcDeferredTaxLiability(0, 0.25)).toBe(0)
    })

    it('零税率: 2000000 × 0 = 0', () => {
      expect(calcDeferredTaxLiability(2000000, 0)).toBe(0)
    })

    it('大数差异: 1e9 × 0.25 = 2.5e8', () => {
      expect(calcDeferredTaxLiability(1e9, 0.25)).toBe(2.5e8)
    })

    it('负差异（可抵扣情况）: -3000000 × 0.25 = -750000', () => {
      expect(calcDeferredTaxLiability(-3000000, 0.25)).toBe(-750000)
    })

    it('小税率: 1000000 × 0.05 = 50000', () => {
      expect(calcDeferredTaxLiability(1000000, 0.05)).toBe(50000)
    })
  })

  // ─── calcDeferredTaxLiabilityRounded ──────────────────────────────────────

  describe('calcDeferredTaxLiabilityRounded（ROUND匹配xlsx）', () => {
    it('整除: 2000000 × 0.25 = 500000.00', () => {
      expect(calcDeferredTaxLiabilityRounded(2000000, 0.25)).toBe(500000)
    })

    it('需四舍五入: 1000001 × 0.25 = 250000.25', () => {
      expect(calcDeferredTaxLiabilityRounded(1000001, 0.25)).toBe(250000.25)
    })

    it('验证ROUND精度: 2000001.555 × 0.25 = 500000.39（四舍五入到2位）', () => {
      // 2000001.555 * 0.25 = 500000.38875 → ROUND(,2) = 500000.39
      expect(calcDeferredTaxLiabilityRounded(2000001.555, 0.25)).toBeCloseTo(500000.39, 2)
    })

    it('零: 0 × 0.25 = 0', () => {
      expect(calcDeferredTaxLiabilityRounded(0, 0.25)).toBe(0)
    })

    it('小额精确: 333.33 × 0.15 = 50.00（ROUND(49.9995,2)=50.00）', () => {
      expect(calcDeferredTaxLiabilityRounded(333.33, 0.15)).toBeCloseTo(50, 2)
    })
  })

  // ─── calcWeightedAvgRate ──────────────────────────────────────────────────

  describe('calcWeightedAvgRate', () => {
    it('正常: [500000,150000] / [2000000,1000000] = 650000/3000000 ≈ 0.2167', () => {
      const rate = calcWeightedAvgRate([500000, 150000], [2000000, 1000000])
      expect(rate).toBeCloseTo(650000 / 3000000, 5)
    })

    it('单一税率: [250000] / [1000000] = 0.25', () => {
      expect(calcWeightedAvgRate([250000], [1000000])).toBeCloseTo(0.25, 5)
    })

    it('空数组: [] / [] = 0', () => {
      expect(calcWeightedAvgRate([], [])).toBe(0)
    })

    it('全零差异: [0,0] / [0,0] = 0（除零保护）', () => {
      expect(calcWeightedAvgRate([0, 0], [0, 0])).toBe(0)
    })

    it('差异为零但税额非零（理论边界）: [100] / [0] = 0', () => {
      // 分母为0应返回0
      expect(calcWeightedAvgRate([100], [0])).toBe(0)
    })

    it('多项目混合税率: [500000,120000,75000] / [2000000,800000,500000] ≈ 0.2106', () => {
      const rate = calcWeightedAvgRate([500000, 120000, 75000], [2000000, 800000, 500000])
      expect(rate).toBeCloseTo(695000 / 3300000, 5)
    })
  })

  // ─── isSpecialNonRecognitionItem ──────────────────────────────────────────

  describe('isSpecialNonRecognitionItem', () => {
    it('"商誉初始确认" → true', () => {
      expect(isSpecialNonRecognitionItem('商誉初始确认')).toBe(true)
    })

    it('"固定资产折旧差异" → false', () => {
      expect(isSpecialNonRecognitionItem('固定资产折旧差异')).toBe(false)
    })

    it('"长期股权投资拟长期持有" → true', () => {
      expect(isSpecialNonRecognitionItem('长期股权投资拟长期持有')).toBe(true)
    })

    it('null → false', () => {
      expect(isSpecialNonRecognitionItem(null)).toBe(false)
    })

    it('undefined → false', () => {
      expect(isSpecialNonRecognitionItem(undefined)).toBe(false)
    })

    it('空字符串 → false', () => {
      expect(isSpecialNonRecognitionItem('')).toBe(false)
    })

    it('"商誉" → true（包含关键词）', () => {
      expect(isSpecialNonRecognitionItem('商誉')).toBe(true)
    })

    it('"长期股权投资" → true（包含关键词）', () => {
      expect(isSpecialNonRecognitionItem('长期股权投资')).toBe(true)
    })

    it('"公允价值变动差异" → false', () => {
      expect(isSpecialNonRecognitionItem('公允价值变动差异')).toBe(false)
    })

    it('"一次性税前扣除差异" → false', () => {
      expect(isSpecialNonRecognitionItem('一次性税前扣除差异')).toBe(false)
    })

    it('"拟长期持有" → true（部分匹配）', () => {
      expect(isSpecialNonRecognitionItem('拟长期持有')).toBe(true)
    })
  })
})
