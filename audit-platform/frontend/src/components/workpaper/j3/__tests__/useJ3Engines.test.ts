/**
 * J3 股份支付 — 公式引擎单元测试
 *
 * 覆盖 useJ3OptionPricingEngine (BS模型数学精度) + useJ3FormulaEngine (费用分摊)
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 2.1-2.6, 3.1-3.6, 4.1-4.4
 */
import { describe, it, expect } from 'vitest'
import {
  normalCDF,
  calcD1,
  calcD2,
  calcBlackScholes,
  validateBSParams,
} from '../../../../composables/workpaper/j3/useJ3OptionPricingEngine'
import {
  calcCumulativeExpense,
  calcVestingExpense,
  calcRemainingExpense,
  calcTotalFairValue,
  calcSubtotal,
  parseNum,
  calcChangeAmount,
  calcChangeRate,
} from '../../../../composables/workpaper/j3/useJ3FormulaEngine'

describe('useJ3OptionPricingEngine', () => {
  describe('normalCDF', () => {
    it('N(0) ≈ 0.5', () => {
      expect(normalCDF(0)).toBeCloseTo(0.5, 6)
    })

    it('N(-∞) → 0, N(+∞) → 1', () => {
      expect(normalCDF(-10)).toBeCloseTo(0, 6)
      expect(normalCDF(10)).toBeCloseTo(1, 6)
    })

    it('N(1.96) ≈ 0.975 (Abramowitz近似)', () => {
      // Abramowitz & Stegun近似 vs 精确值差异<0.01
      expect(normalCDF(1.96)).toBeGreaterThan(0.97)
      expect(normalCDF(1.96)).toBeLessThan(0.99)
    })

    it('对称性: N(x) + N(-x) ≈ 1', () => {
      expect(normalCDF(1.5) + normalCDF(-1.5)).toBeCloseTo(1, 6)
    })
  })

  describe('calcD1', () => {
    it('已知参数验证', () => {
      // S=100, K=100, T=1, r=0.05, σ=0.2
      // d1 = [ln(1) + (0.05 + 0.02)×1] / (0.2×1) = 0.07/0.2 = 0.35
      const d1 = calcD1(100, 100, 1, 0.05, 0.2)
      expect(d1).toBeCloseTo(0.35, 4)
    })
  })

  describe('calcD2', () => {
    it('d2 = d1 - σ√T', () => {
      const d2 = calcD2(0.35, 0.2, 1)
      expect(d2).toBeCloseTo(0.15, 4)
    })
  })

  describe('calcBlackScholes', () => {
    it('平值期权(S=K=100, T=1, r=5%, σ=20%)', () => {
      // BS价格约 10~12 范围（Abramowitz CDF近似略有偏差）
      const price = calcBlackScholes(100, 100, 1, 0.05, 0.2)
      expect(price).toBeGreaterThan(10)
      expect(price).toBeLessThan(13)
    })

    it('深度实值(S=200, K=100) → 接近内在价值', () => {
      const price = calcBlackScholes(200, 100, 1, 0.05, 0.2)
      expect(price).toBeGreaterThan(95) // 内在价值=100，加上时间价值
    })

    it('深度虚值(S=50, K=100) → 接近0', () => {
      const price = calcBlackScholes(50, 100, 1, 0.05, 0.2)
      expect(price).toBeLessThan(1)
    })

    it('价格非负', () => {
      expect(calcBlackScholes(100, 150, 0.5, 0.03, 0.3)).toBeGreaterThanOrEqual(0)
    })

    it('S增加→价格增加（delta正）', () => {
      const p1 = calcBlackScholes(100, 100, 1, 0.05, 0.3)
      const p2 = calcBlackScholes(110, 100, 1, 0.05, 0.3)
      expect(p2).toBeGreaterThan(p1)
    })
  })

  describe('validateBSParams', () => {
    it('合理参数返回isValid=true', () => {
      const result = validateBSParams({ S: 50, K: 50, T: 3, r: 0.03, sigma: 0.35 })
      expect(result.isValid).toBe(true)
    })

    it('S≤0返回isValid=false', () => {
      const result = validateBSParams({ S: 0, K: 50, T: 3, r: 0.03, sigma: 0.35 })
      expect(result.isValid).toBe(false)
      expect(result.warnings).toContain('标的价格必须大于0')
    })

    it('sigma过高生成审计关注警告', () => {
      const result = validateBSParams({ S: 50, K: 50, T: 3, r: 0.03, sigma: 1.5 })
      expect(result.isValid).toBe(true) // 仍可计算
      expect(result.warnings.some(w => w.includes('波动率超过100%'))).toBe(true)
    })
  })
})

describe('useJ3FormulaEngine', () => {
  describe('parseNum', () => {
    it('正常数字', () => expect(parseNum(42)).toBe(42))
    it('字符串数字', () => expect(parseNum('3.14')).toBe(3.14))
    it('null → 0', () => expect(parseNum(null)).toBe(0))
    it('undefined → 0', () => expect(parseNum(undefined)).toBe(0))
    it('空串 → 0', () => expect(parseNum('')).toBe(0))
    it('NaN → 0', () => expect(parseNum(NaN)).toBe(0))
    it('Infinity → 0', () => expect(parseNum(Infinity)).toBe(0))
  })

  describe('calcCumulativeExpense', () => {
    it('等待期中间: 100万 × (2/4) = 50万', () => {
      expect(calcCumulativeExpense(1000000, 4, 2)).toBeCloseTo(500000)
    })

    it('等待期满: 100万 × MIN(5/4, 1) = 100万', () => {
      expect(calcCumulativeExpense(1000000, 4, 5)).toBeCloseTo(1000000)
    })

    it('未开始: serviceYears=0 → 0', () => {
      expect(calcCumulativeExpense(1000000, 4, 0)).toBe(0)
    })

    it('totalFV≤0 → 0', () => {
      expect(calcCumulativeExpense(0, 4, 2)).toBe(0)
      expect(calcCumulativeExpense(-100, 4, 2)).toBe(0)
    })
  })

  describe('calcVestingExpense', () => {
    it('本期费用 = 累计 - 以前累计', () => {
      // 总FV=100万, 等待期4年, 已服务2年, 以前累计25万
      // 累计 = 100万 × 2/4 = 50万; 本期 = 50万 - 25万 = 25万
      expect(calcVestingExpense(1000000, 4, 2, 250000)).toBeCloseTo(250000)
    })

    it('等待期满后不再确认新费用', () => {
      // 累计已达100万, 本期=100万-100万=0
      expect(calcVestingExpense(1000000, 4, 5, 1000000)).toBeCloseTo(0)
    })
  })

  describe('calcRemainingExpense', () => {
    it('剩余 = 总FV - 累计', () => {
      expect(calcRemainingExpense(1000000, 600000)).toBeCloseTo(400000)
    })

    it('全部确认后剩余为0', () => {
      expect(calcRemainingExpense(1000000, 1000000)).toBeCloseTo(0)
    })
  })

  describe('calcTotalFairValue', () => {
    it('10元 × 50000份 = 500000', () => {
      expect(calcTotalFairValue(10, 50000)).toBe(500000)
    })
  })

  describe('calcSubtotal', () => {
    it('正常求和', () => expect(calcSubtotal([1, 2, 3, 4, 5])).toBe(15))
    it('空数组', () => expect(calcSubtotal([])).toBe(0))
    it('含负数', () => expect(calcSubtotal([100, -50, 30])).toBe(80))
  })

  describe('calcChangeAmount', () => {
    it('增长', () => expect(calcChangeAmount(150, 100)).toBe(50))
    it('减少', () => expect(calcChangeAmount(80, 100)).toBe(-20))
  })

  describe('calcChangeRate', () => {
    it('正常变动率', () => expect(calcChangeRate(100, 130)).toBeCloseTo(0.3))
    it('期初=0且期末=0 → 空', () => expect(calcChangeRate(0, 0)).toBe(''))
    it('期初=0且期末≠0 → N/A', () => expect(calcChangeRate(0, 50)).toBe('N/A'))
  })
})
