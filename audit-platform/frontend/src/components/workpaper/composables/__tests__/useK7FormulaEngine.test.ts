/**
 * useK7FormulaEngine — Vitest 单元测试
 *
 * 覆盖 K7 递延收益公式引擎全部纯函数的核心逻辑和边界情况。
 * 科目：2401递延收益（贷方/负债类）
 *
 * Spec: .kiro/specs/k7-deferred-income/ Task 7.1
 * Requirements: CP-K7-01, CP-K7-02, CP-K7-06
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '../useK7FormulaEngine'

describe('useK7FormulaEngine', () => {
  // ─── calcAuditedAmount ─────────────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('正常：未审100 + AJE20 + RJE(-10) = 110', () => {
      expect(calcAuditedAmount(100, 20, -10)).toBe(110)
    })

    it('全零：0 + 0 + 0 = 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负数AJE：500000 + (-30000) + 0 = 470000', () => {
      expect(calcAuditedAmount(500000, -30000, 0)).toBe(470000)
    })

    it('NaN输入视为0', () => {
      expect(calcAuditedAmount(NaN, 100, 200)).toBe(300)
      expect(calcAuditedAmount(100, NaN, 200)).toBe(300)
      expect(calcAuditedAmount(100, 200, NaN)).toBe(300)
    })

    it('大金额精度：1234567890.12 + 0.01 + 0.01', () => {
      expect(calcAuditedAmount(1234567890.12, 0.01, 0.01)).toBeCloseTo(1234567890.14, 2)
    })
  })

  // ─── calcLiabilityEndBalance ───────────────────────────────────────────────

  describe('calcLiabilityEndBalance', () => {
    it('负债类正常：期初500000 + 收到200000 - 分摊100000 = 600000', () => {
      expect(calcLiabilityEndBalance(500000, 200000, 100000)).toBe(600000)
    })

    it('无收到无分摊：期末=期初', () => {
      expect(calcLiabilityEndBalance(300000, 0, 0)).toBe(300000)
    })

    it('只分摊：期初800000 + 0 - 150000 = 650000', () => {
      expect(calcLiabilityEndBalance(800000, 0, 150000)).toBe(650000)
    })

    it('分摊>期初+收到→允许负数（由UI层兜底）', () => {
      // 公式引擎不兜底，只做数学计算
      expect(calcLiabilityEndBalance(100000, 0, 200000)).toBe(-100000)
    })

    it('NaN输入视为0', () => {
      expect(calcLiabilityEndBalance(NaN, 100, 50)).toBe(50)
      expect(calcLiabilityEndBalance(100, NaN, 50)).toBe(50)
      expect(calcLiabilityEndBalance(100, 50, NaN)).toBe(150)
    })

    it('期初=0场景（新增补助项目）', () => {
      expect(calcLiabilityEndBalance(0, 1000000, 0)).toBe(1000000)
    })
  })

  // ─── calcSubtotal ──────────────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('正常求和：[100, 200, 300] = 600', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })

    it('空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素：[500000] = 500000', () => {
      expect(calcSubtotal([500000])).toBe(500000)
    })

    it('含负数：[100, -50, 200, -30] = 220', () => {
      expect(calcSubtotal([100, -50, 200, -30])).toBe(220)
    })

    it('含NaN视为0：[100, NaN, 200] = 300', () => {
      expect(calcSubtotal([100, NaN, 200])).toBe(300)
    })

    it('大数组正确求和', () => {
      const arr = Array.from({ length: 50 }, (_, i) => i + 1)
      // Σ(1..50) = 50*51/2 = 1275
      expect(calcSubtotal(arr)).toBe(1275)
    })
  })
})
