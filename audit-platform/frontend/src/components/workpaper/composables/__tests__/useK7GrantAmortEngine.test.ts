/**
 * useK7GrantAmortEngine — Vitest 单元测试
 *
 * 覆盖政府补助分摊引擎全部纯函数的核心逻辑和边界情况。
 * CAS16 政府补助分摊测算：直线分摊、期末余额、测算差异
 */
import { describe, it, expect } from 'vitest'
import {
  calcStraightLineAmort,
  calcRemainingBalance,
  calcAmortVariance,
} from '../useK7GrantAmortEngine'

describe('useK7GrantAmortEngine', () => {
  // ─── calcStraightLineAmort ──────────────────────────────────────────────────

  describe('calcStraightLineAmort', () => {
    it('正常直线分摊：1200000 / 120月 × 12月 = 120000', () => {
      expect(calcStraightLineAmort(1200000, 120, 12)).toBe(120000)
    })

    it('非整除：1000000 / 36月 × 6月', () => {
      // 1000000 / 36 * 6 = 166666.6667
      expect(calcStraightLineAmort(1000000, 36, 6)).toBeCloseTo(166666.6667, 2)
    })

    it('totalPeriods=0 → 返回0（除零兜底）', () => {
      expect(calcStraightLineAmort(500000, 0, 12)).toBe(0)
    })

    it('currentPeriods=0 → 返回0（本期无分摊）', () => {
      expect(calcStraightLineAmort(500000, 60, 0)).toBe(0)
    })

    it('total=0 → 返回0', () => {
      expect(calcStraightLineAmort(0, 120, 12)).toBe(0)
    })

    it('NaN输入视为0', () => {
      expect(calcStraightLineAmort(NaN, 120, 12)).toBe(0)
      expect(calcStraightLineAmort(1000000, NaN, 12)).toBe(0)
      expect(calcStraightLineAmort(1000000, 120, NaN)).toBe(0)
    })
  })

  // ─── calcRemainingBalance ───────────────────────────────────────────────────

  describe('calcRemainingBalance', () => {
    it('正常期末余额：1000000 - 300000 = 700000', () => {
      expect(calcRemainingBalance(1000000, 300000)).toBe(700000)
    })

    it('全部摊完：500000 - 500000 = 0', () => {
      expect(calcRemainingBalance(500000, 500000)).toBe(0)
    })

    it('accumulated > total → 返回0（兜底，不允许负数）', () => {
      expect(calcRemainingBalance(500000, 600000)).toBe(0)
    })

    it('accumulated=0 → 余额=total', () => {
      expect(calcRemainingBalance(800000, 0)).toBe(800000)
    })

    it('NaN输入视为0', () => {
      expect(calcRemainingBalance(NaN, 300000)).toBe(0)
      expect(calcRemainingBalance(1000000, NaN)).toBe(1000000)
    })
  })

  // ─── calcAmortVariance ──────────────────────────────────────────────────────

  describe('calcAmortVariance', () => {
    it('正差异（企业少摊）：150000 - 120000 = 30000', () => {
      expect(calcAmortVariance(150000, 120000)).toBe(30000)
    })

    it('负差异（企业多摊）：100000 - 130000 = -30000', () => {
      expect(calcAmortVariance(100000, 130000)).toBe(-30000)
    })

    it('无差异：200000 - 200000 = 0', () => {
      expect(calcAmortVariance(200000, 200000)).toBe(0)
    })

    it('NaN输入视为0', () => {
      expect(calcAmortVariance(NaN, 100000)).toBe(-100000)
      expect(calcAmortVariance(100000, NaN)).toBe(100000)
    })
  })
})
