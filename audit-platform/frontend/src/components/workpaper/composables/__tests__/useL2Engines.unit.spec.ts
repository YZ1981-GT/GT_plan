/**
 * Unit Tests — L2 应付利息公式引擎 + 计提核对引擎
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 7.1
 *
 * 已知值验证，互补 PBT 测试（useL2Engines.pbt.spec.ts）。
 * 覆盖 Properties P1~P5 的具体场景。
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '../useL2FormulaEngine'
import {
  calcAccrualDiff,
  aggregateBySource,
  type InterestDetail,
} from '../useL2AccrualEngine'

// ─── useL2FormulaEngine ─────────────────────────────────────────────────────

describe('useL2FormulaEngine', () => {
  // ── calcAuditedAmount (P1) ──────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('已知值: 1000 + 200 + (-50) = 1150', () => {
      expect(calcAuditedAmount(1000, 200, -50)).toBe(1150)
    })

    it('全零: 0 + 0 + 0 = 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })
  })

  // ── calcLiabilityEndBalance (P2) ────────────────────────────────────────

  describe('calcLiabilityEndBalance', () => {
    it('负债类方向: 1000 + 500 - 200 = 1300', () => {
      expect(calcLiabilityEndBalance(1000, 500, 200)).toBe(1300)
    })

    it('全零: 0 + 0 - 0 = 0', () => {
      expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
    })

    it('结果可为负: 0 + 0 - 100 = -100', () => {
      expect(calcLiabilityEndBalance(0, 0, 100)).toBe(-100)
    })
  })

  // ── calcSubtotal (P4) ──────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('已知值: [100, 200, 300] = 600', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })

    it('空数组: [] = 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('含负数: [100, -50, 200, -30] = 220', () => {
      expect(calcSubtotal([100, -50, 200, -30])).toBe(220)
    })
  })
})

// ─── useL2AccrualEngine ─────────────────────────────────────────────────────

describe('useL2AccrualEngine', () => {
  // ── calcAccrualDiff (P3) ────────────────────────────────────────────────

  describe('calcAccrualDiff', () => {
    it('正差异（少计提）: 1500 - 1000 = 500', () => {
      expect(calcAccrualDiff(1500, 1000)).toBe(500)
    })

    it('负差异（多计提）: 800 - 1000 = -200', () => {
      expect(calcAccrualDiff(800, 1000)).toBe(-200)
    })

    it('零差异: 1000 - 1000 = 0', () => {
      expect(calcAccrualDiff(1000, 1000)).toBe(0)
    })
  })

  // ── aggregateBySource (P5) ──────────────────────────────────────────────

  describe('aggregateBySource', () => {
    it('按来源分组汇总', () => {
      const details: InterestDetail[] = [
        { source: '短期借款', amount: 100 },
        { source: '长期借款', amount: 200 },
        { source: '短期借款', amount: 300 },
      ]
      const result = aggregateBySource(details)
      expect(result).toEqual({ '短期借款': 400, '长期借款': 200 })
    })

    it('空数组 → {}', () => {
      expect(aggregateBySource([])).toEqual({})
    })

    it('守恒性: 输出值之和 = 输入金额之和', () => {
      const details: InterestDetail[] = [
        { source: '短期借款', amount: 150 },
        { source: '长期借款', amount: 250 },
        { source: '应付债券', amount: 100 },
        { source: '短期借款', amount: 50 },
      ]
      const result = aggregateBySource(details)
      const outputSum = Object.values(result).reduce((a, b) => a + b, 0)
      const inputSum = details.reduce((a, d) => a + d.amount, 0)
      expect(outputSum).toBe(inputSum)
    })
  })
})
