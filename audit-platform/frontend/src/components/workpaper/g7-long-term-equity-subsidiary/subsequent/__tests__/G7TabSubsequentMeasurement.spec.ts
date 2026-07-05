import { describe, it, expect } from 'vitest'
import {
  calcCostMethodIncome,
  calcSubsequentBalance,
  parseNum,
} from '../../../composables/useG7SubFormulaEngine'

/**
 * G7-10 子公司后续计量测试表 单元测试
 *
 * 验证:
 * - 投资收益 = 被投资方宣告股利 × 持股比例 (Requirements 4.2)
 * - 期末账面 = 期初 + 追加投资 - 减值计提 (Requirements 4.3)
 * - 差异 = 期末余额(计算) - 企业账面期末
 * - 边界情况: 所有值为0时正确返回0
 */

describe('G7TabSubsequentMeasurement — 公式验证', () => {
  // ─── 投资收益公式 (Requirements 4.2) ─────────────────────────────────────

  describe('calcCostMethodIncome: 投资收益 = 股利 × 持股比例', () => {
    it('基本计算: 1000万股利 × 60%持股 = 600万', () => {
      expect(calcCostMethodIncome(10_000_000, 0.6)).toBe(6_000_000)
    })

    it('小额股利: 50000 × 0.51 = 25500', () => {
      expect(calcCostMethodIncome(50_000, 0.51)).toBe(25_500)
    })

    it('100%持股: 股利全额确认', () => {
      expect(calcCostMethodIncome(200_000, 1)).toBe(200_000)
    })

    it('小比例持股: 1000000 × 0.05 = 50000', () => {
      expect(calcCostMethodIncome(1_000_000, 0.05)).toBe(50_000)
    })

    it('精度处理: 333333 × 0.3333 应四舍五入到分', () => {
      const result = calcCostMethodIncome(333_333, 0.3333)
      // 333333 × 0.3333 = 111,099.8889 → round to 2 decimals = 111099.89
      expect(result).toBe(111_099.89)
    })

    it('股利为0时投资收益=0', () => {
      expect(calcCostMethodIncome(0, 0.6)).toBe(0)
    })

    it('持股比例为0时投资收益=0', () => {
      expect(calcCostMethodIncome(500_000, 0)).toBe(0)
    })
  })

  // ─── 期末账面公式 (Requirements 4.3) ──────────────────────────────────────

  describe('calcSubsequentBalance: 期末账面 = 期初 + 追加 - 减值', () => {
    it('基本计算: 1000 + 200 - 50 = 1150', () => {
      expect(calcSubsequentBalance(1_000, 200, 50)).toBe(1_150)
    })

    it('无追加无减值: 期末=期初', () => {
      expect(calcSubsequentBalance(5_000_000, 0, 0)).toBe(5_000_000)
    })

    it('仅追加投资: 3000000 + 1000000 - 0 = 4000000', () => {
      expect(calcSubsequentBalance(3_000_000, 1_000_000, 0)).toBe(4_000_000)
    })

    it('仅减值: 8000000 + 0 - 2000000 = 6000000', () => {
      expect(calcSubsequentBalance(8_000_000, 0, 2_000_000)).toBe(6_000_000)
    })

    it('大额计算: 100000000 + 50000000 - 10000000 = 140000000', () => {
      expect(calcSubsequentBalance(100_000_000, 50_000_000, 10_000_000)).toBe(140_000_000)
    })

    it('精度处理: 含小数的金额正确计算', () => {
      const result = calcSubsequentBalance(1_000_000.55, 200_000.33, 50_000.11)
      // 1000000.55 + 200000.33 - 50000.11 = 1150000.77
      expect(result).toBe(1_150_000.77)
    })
  })

  // ─── 差异计算 ─────────────────────────────────────────────────────────────

  describe('差异: variance = closingBalance - companyEndingBalance', () => {
    it('无差异: 计算期末=企业期末', () => {
      const closingBalance = calcSubsequentBalance(1_000_000, 200_000, 50_000)
      const companyEndingBalance = 1_150_000
      const variance = Math.round((closingBalance - parseNum(companyEndingBalance)) * 100) / 100
      expect(variance).toBe(0)
    })

    it('正差异: 计算期末 > 企业期末', () => {
      const closingBalance = calcSubsequentBalance(1_000_000, 200_000, 50_000) // 1150000
      const companyEndingBalance = 1_100_000
      const variance = Math.round((closingBalance - parseNum(companyEndingBalance)) * 100) / 100
      expect(variance).toBe(50_000)
    })

    it('负差异: 计算期末 < 企业期末', () => {
      const closingBalance = calcSubsequentBalance(1_000_000, 0, 100_000) // 900000
      const companyEndingBalance = 1_000_000
      const variance = Math.round((closingBalance - parseNum(companyEndingBalance)) * 100) / 100
      expect(variance).toBe(-100_000)
    })

    it('含小数差异精确到分', () => {
      const closingBalance = calcSubsequentBalance(500_000.50, 100_000.25, 0) // 600000.75
      const companyEndingBalance = 600_000.50
      const variance = Math.round((closingBalance - parseNum(companyEndingBalance)) * 100) / 100
      expect(variance).toBe(0.25)
    })
  })

  // ─── 边界情况 ─────────────────────────────────────────────────────────────

  describe('边界情况: 所有值为0时正确返回0', () => {
    it('calcCostMethodIncome(0, 0) = 0', () => {
      expect(calcCostMethodIncome(0, 0)).toBe(0)
    })

    it('calcSubsequentBalance(0, 0, 0) = 0', () => {
      expect(calcSubsequentBalance(0, 0, 0)).toBe(0)
    })

    it('差异计算: 两个0相减=0', () => {
      const closingBalance = calcSubsequentBalance(0, 0, 0)
      const companyEndingBalance = 0
      const variance = Math.round((closingBalance - parseNum(companyEndingBalance)) * 100) / 100
      expect(variance).toBe(0)
    })

    it('parseNum对边界值正确处理', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
      expect(parseNum('  ')).toBe(0)
      expect(parseNum('abc')).toBe(0)
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(0)).toBe(0)
      expect(parseNum(42.5)).toBe(42.5)
    })
  })
})
