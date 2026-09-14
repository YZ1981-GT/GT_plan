/**
 * N2 应交税费 — 单元测试：useN2FormulaEngine + useN2VatEngine + useN2MultiTaxEngine
 *
 * Spec: .kiro/specs/n2-taxes-payable/ Task 7.1
 * Requirements: P1-P9
 *
 * 覆盖：
 * - calcAuditedAmount: 审定数=未审+AJE+RJE
 * - calcLiabilityEndBalance: 负债类期末=期初+贷方-借方（NOT 期初+借-贷！）
 * - calcSubtotal: 合计行恒等
 * - calcDiff: 账面vs申报表差异
 * - calcOutputVat: 销项税额=销售额×税率
 * - calcPayableVat: 应交增值税=销项-(进项-进项转出)
 * - calcVatBurdenRate: 增值税税负率
 * - calcSurtax: 城建税及附加=(增值税+消费税)×税率
 * - calcPropertyTaxByValue: 房产税从价=原值×(1-扣除比例)×1.2%
 * - calcPropertyTaxByRent: 房产税从租=租金×12%
 * - calcLandVat: 土增税=增值额×税率-扣除项目×速算扣除系数
 * - calcAppreciationRate: 土增税增值率=增值额/扣除项目
 *
 * 边界：零值/大数/税率边界/留抵/除零
 */
import { describe, it, expect } from 'vitest'

import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcDiff,
} from '../composables/useN2FormulaEngine'

import {
  calcOutputVat,
  calcPayableVat,
  calcVatBurdenRate,
} from '../composables/useN2VatEngine'

import {
  calcSurtax,
  calcPropertyTaxByValue,
  calcPropertyTaxByRent,
  calcLandVat,
  calcAppreciationRate,
} from '../composables/useN2MultiTaxEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// useN2FormulaEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN2FormulaEngine', () => {
  // ─── calcAuditedAmount (P1) ───────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('基本加法: 100 + 20 + 10 = 130', () => {
      expect(calcAuditedAmount(100, 20, 10)).toBe(130)
    })

    it('零值: 0 + 0 + 0 = 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负AJE调减: 1000 + (-50) + 0 = 950', () => {
      expect(calcAuditedAmount(1000, -50, 0)).toBe(950)
    })

    it('负RJE重分类: 500 + 0 + (-200) = 300', () => {
      expect(calcAuditedAmount(500, 0, -200)).toBe(300)
    })

    it('全负值: -100 + (-20) + (-30) = -150', () => {
      expect(calcAuditedAmount(-100, -20, -30)).toBe(-150)
    })

    it('大数: 1e9 + 1e8 + 1e7 = 1.11e9', () => {
      expect(calcAuditedAmount(1e9, 1e8, 1e7)).toBe(1.11e9)
    })

    it('小数精度: 100.55 + 20.33 + 10.12 ≈ 131', () => {
      expect(calcAuditedAmount(100.55, 20.33, 10.12)).toBeCloseTo(131, 2)
    })
  })

  // ─── calcLiabilityEndBalance (P2) ─────────────────────────────────────────

  describe('calcLiabilityEndBalance（负债类：期初+贷方-借方）', () => {
    it('基本: 期初1000+贷方500-借方200 = 1300', () => {
      expect(calcLiabilityEndBalance(1000, 500, 200)).toBe(1300)
    })

    it('零值: 0+0-0 = 0', () => {
      expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
    })

    it('全部缴纳: 1000+0-1000 = 0（期初全缴完）', () => {
      expect(calcLiabilityEndBalance(1000, 0, 1000)).toBe(0)
    })

    it('只有计提: 0+500-0 = 500', () => {
      expect(calcLiabilityEndBalance(0, 500, 0)).toBe(500)
    })

    it('缴纳大于期初+计提（负余额罕见但可能）: 100+50-200 = -50', () => {
      expect(calcLiabilityEndBalance(100, 50, 200)).toBe(-50)
    })

    it('大数: 1e9+5e8-3e8 = 1.2e9', () => {
      expect(calcLiabilityEndBalance(1e9, 5e8, 3e8)).toBe(1.2e9)
    })

    it('方向验证：不是期初+借-贷（确保负债类方向正确）', () => {
      // 负债类：期末 = 期初+贷-借 = 1000+300-100 = 1200
      // 如果错成资产类 期初+借-贷 = 1000+100-300 = 800（错误）
      const result = calcLiabilityEndBalance(1000, 300, 100)
      expect(result).toBe(1200) // 正确：期初+贷-借
      expect(result).not.toBe(800) // 不是资产类方向
    })

    it('小数精度: 999.99 + 100.01 - 50.005 ≈ 1049.995', () => {
      expect(calcLiabilityEndBalance(999.99, 100.01, 50.005)).toBeCloseTo(1049.995, 2)
    })
  })

  // ─── calcSubtotal (P8) ────────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('空数组: [] = 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素: [100] = 100', () => {
      expect(calcSubtotal([100])).toBe(100)
    })

    it('多元素: [100, 200, 300] = 600', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })

    it('含负数: [100, -50, 200] = 250', () => {
      expect(calcSubtotal([100, -50, 200])).toBe(250)
    })

    it('全零: [0, 0, 0, 0] = 0', () => {
      expect(calcSubtotal([0, 0, 0, 0])).toBe(0)
    })

    it('大数数组: [1e9, 2e9, 3e9] = 6e9', () => {
      expect(calcSubtotal([1e9, 2e9, 3e9])).toBe(6e9)
    })
  })

  // ─── calcDiff ─────────────────────────────────────────────────────────────

  describe('calcDiff（账面-申报表）', () => {
    it('正差异: 账面>申报表 → 正值(可能多计提)', () => {
      expect(calcDiff(1000, 800)).toBe(200)
    })

    it('负差异: 账面<申报表 → 负值(可能少计提)', () => {
      expect(calcDiff(800, 1000)).toBe(-200)
    })

    it('零差异: 账面=申报表', () => {
      expect(calcDiff(500, 500)).toBe(0)
    })

    it('零值: 0 - 0 = 0', () => {
      expect(calcDiff(0, 0)).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useN2VatEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN2VatEngine', () => {
  // ─── calcOutputVat (P3) ───────────────────────────────────────────────────

  describe('calcOutputVat（销项税额=销售额×税率）', () => {
    it('13%税率: 1000000 × 0.13 = 130000', () => {
      expect(calcOutputVat(1000000, 0.13)).toBeCloseTo(130000, 2)
    })

    it('9%税率: 500000 × 0.09 = 45000', () => {
      expect(calcOutputVat(500000, 0.09)).toBeCloseTo(45000, 2)
    })

    it('6%税率: 200000 × 0.06 = 12000', () => {
      expect(calcOutputVat(200000, 0.06)).toBeCloseTo(12000, 2)
    })

    it('3%小规模: 100000 × 0.03 = 3000', () => {
      expect(calcOutputVat(100000, 0.03)).toBeCloseTo(3000, 2)
    })

    it('零销售额: 0 × 0.13 = 0', () => {
      expect(calcOutputVat(0, 0.13)).toBe(0)
    })

    it('零税率: 1000000 × 0 = 0', () => {
      expect(calcOutputVat(1000000, 0)).toBe(0)
    })

    it('大数: 1e9 × 0.13 = 1.3e8', () => {
      expect(calcOutputVat(1e9, 0.13)).toBeCloseTo(1.3e8, 0)
    })
  })

  // ─── calcPayableVat (P4) ──────────────────────────────────────────────────

  describe('calcPayableVat（应交增值税=销项-(进项-进项转出)）', () => {
    it('正常: 130000-(100000-5000) = 35000', () => {
      expect(calcPayableVat(130000, 100000, 5000)).toBe(35000)
    })

    it('无进项转出: 130000-(100000-0) = 30000', () => {
      expect(calcPayableVat(130000, 100000, 0)).toBe(30000)
    })

    it('留抵（进项>销项）: 50000-(100000-0) = -50000', () => {
      // 留抵税额：进项大于销项，结果为负
      expect(calcPayableVat(50000, 100000, 0)).toBe(-50000)
    })

    it('零值: 0-(0-0) = 0', () => {
      expect(calcPayableVat(0, 0, 0)).toBe(0)
    })

    it('全额抵扣: 100000-(100000-0) = 0', () => {
      expect(calcPayableVat(100000, 100000, 0)).toBe(0)
    })

    it('进项转出等于进项: 100000-(50000-50000) = 100000', () => {
      // 进项全部转出，相当于无可抵扣进项
      expect(calcPayableVat(100000, 50000, 50000)).toBe(100000)
    })
  })

  // ─── calcVatBurdenRate ────────────────────────────────────────────────────

  describe('calcVatBurdenRate（税负率=应交增值税/销售额）', () => {
    it('正常: 35000/1000000 = 0.035 (3.5%)', () => {
      expect(calcVatBurdenRate(35000, 1000000)).toBeCloseTo(0.035, 5)
    })

    it('零分母: 35000/0 = 0（避免除零）', () => {
      expect(calcVatBurdenRate(35000, 0)).toBe(0)
    })

    it('零分子: 0/1000000 = 0', () => {
      expect(calcVatBurdenRate(0, 1000000)).toBe(0)
    })

    it('负值（留抵）: -50000/1000000 = -0.05', () => {
      expect(calcVatBurdenRate(-50000, 1000000)).toBeCloseTo(-0.05, 5)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useN2MultiTaxEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN2MultiTaxEngine', () => {
  // ─── calcSurtax (P5) ──────────────────────────────────────────────────────

  describe('calcSurtax（城建税及附加=(增值税+消费税)×税率）', () => {
    it('城建税市区7%: (100000+0)×0.07 = 7000', () => {
      expect(calcSurtax(100000, 0, 0.07)).toBeCloseTo(7000, 2)
    })

    it('城建税县城5%: (100000+0)×0.05 = 5000', () => {
      expect(calcSurtax(100000, 0, 0.05)).toBeCloseTo(5000, 2)
    })

    it('城建税其他1%: (100000+0)×0.01 = 1000', () => {
      expect(calcSurtax(100000, 0, 0.01)).toBeCloseTo(1000, 2)
    })

    it('教育费附加3%: (100000+0)×0.03 = 3000', () => {
      expect(calcSurtax(100000, 0, 0.03)).toBeCloseTo(3000, 2)
    })

    it('地方教育附加2%: (100000+0)×0.02 = 2000', () => {
      expect(calcSurtax(100000, 0, 0.02)).toBeCloseTo(2000, 2)
    })

    it('含消费税: (100000+20000)×0.07 = 8400', () => {
      expect(calcSurtax(100000, 20000, 0.07)).toBeCloseTo(8400, 2)
    })

    it('零值: (0+0)×0.07 = 0', () => {
      expect(calcSurtax(0, 0, 0.07)).toBe(0)
    })

    it('零税率: (100000+0)×0 = 0', () => {
      expect(calcSurtax(100000, 0, 0)).toBe(0)
    })
  })

  // ─── calcPropertyTaxByValue (P6) ──────────────────────────────────────────

  describe('calcPropertyTaxByValue（房产税从价=原值×(1-扣除比例)×1.2%）', () => {
    it('标准30%扣除(北京): 10000000×(1-0.3)×0.012 = 84000', () => {
      expect(calcPropertyTaxByValue(10000000, 0.3)).toBeCloseTo(84000, 2)
    })

    it('20%扣除(广东): 10000000×(1-0.2)×0.012 = 96000', () => {
      expect(calcPropertyTaxByValue(10000000, 0.2)).toBeCloseTo(96000, 2)
    })

    it('10%扣除: 10000000×(1-0.1)×0.012 = 108000', () => {
      expect(calcPropertyTaxByValue(10000000, 0.1)).toBeCloseTo(108000, 2)
    })

    it('零扣除比例: 1000000×(1-0)×0.012 = 12000', () => {
      expect(calcPropertyTaxByValue(1000000, 0)).toBeCloseTo(12000, 2)
    })

    it('零原值: 0×(1-0.3)×0.012 = 0', () => {
      expect(calcPropertyTaxByValue(0, 0.3)).toBe(0)
    })

    it('大数: 1e9×(1-0.3)×0.012 = 8400000', () => {
      expect(calcPropertyTaxByValue(1e9, 0.3)).toBeCloseTo(8400000, 0)
    })
  })

  // ─── calcPropertyTaxByRent ────────────────────────────────────────────────

  describe('calcPropertyTaxByRent（房产税从租=租金×12%）', () => {
    it('正常: 1000000×0.12 = 120000', () => {
      expect(calcPropertyTaxByRent(1000000)).toBeCloseTo(120000, 2)
    })

    it('零租金: 0×0.12 = 0', () => {
      expect(calcPropertyTaxByRent(0)).toBe(0)
    })

    it('小额租金: 5000×0.12 = 600', () => {
      expect(calcPropertyTaxByRent(5000)).toBeCloseTo(600, 2)
    })
  })

  // ─── calcLandVat (P7) ─────────────────────────────────────────────────────

  describe('calcLandVat（土增税=增值额×税率-扣除项目×速算扣除系数）', () => {
    it('第一档≤50%: 增值额500000×0.30-扣除项目1000000×0 = 150000', () => {
      // 增值率50%, 税率30%, 速算系数0
      expect(calcLandVat(500000, 0.30, 1000000, 0)).toBeCloseTo(150000, 2)
    })

    it('第二档50%~100%: 增值额800000×0.40-扣除项目1000000×0.05 = 270000', () => {
      // 增值率80%, 税率40%, 速算系数5%
      expect(calcLandVat(800000, 0.40, 1000000, 0.05)).toBeCloseTo(270000, 2)
    })

    it('第三档100%~200%: 增值额1500000×0.50-扣除项目1000000×0.15 = 600000', () => {
      // 增值率150%, 税率50%, 速算系数15%
      expect(calcLandVat(1500000, 0.50, 1000000, 0.15)).toBeCloseTo(600000, 2)
    })

    it('第四档>200%: 增值额2500000×0.60-扣除项目1000000×0.35 = 1150000', () => {
      // 增值率250%, 税率60%, 速算系数35%
      expect(calcLandVat(2500000, 0.60, 1000000, 0.35)).toBeCloseTo(1150000, 2)
    })

    it('零增值额: 0×0.30-1000000×0 = 0', () => {
      expect(calcLandVat(0, 0.30, 1000000, 0)).toBe(0)
    })

    it('零扣除项目+零速算: 500000×0.30-0×0 = 150000', () => {
      expect(calcLandVat(500000, 0.30, 0, 0)).toBeCloseTo(150000, 2)
    })
  })

  // ─── calcAppreciationRate (P9) ────────────────────────────────────────────

  describe('calcAppreciationRate（增值率=增值额/扣除项目）', () => {
    it('正常50%: 500000/1000000 = 0.5', () => {
      expect(calcAppreciationRate(500000, 1000000)).toBeCloseTo(0.5, 5)
    })

    it('100%: 1000000/1000000 = 1.0', () => {
      expect(calcAppreciationRate(1000000, 1000000)).toBeCloseTo(1.0, 5)
    })

    it('200%: 2000000/1000000 = 2.0', () => {
      expect(calcAppreciationRate(2000000, 1000000)).toBeCloseTo(2.0, 5)
    })

    it('300%: 3000000/1000000 = 3.0', () => {
      expect(calcAppreciationRate(3000000, 1000000)).toBeCloseTo(3.0, 5)
    })

    it('零分母: 500000/0 = 0（避免除零）', () => {
      expect(calcAppreciationRate(500000, 0)).toBe(0)
    })

    it('零分子: 0/1000000 = 0', () => {
      expect(calcAppreciationRate(0, 1000000)).toBe(0)
    })

    it('小增值率: 100000/1000000 = 0.1 (10%)', () => {
      expect(calcAppreciationRate(100000, 1000000)).toBeCloseTo(0.1, 5)
    })
  })
})
