/**
 * Unit Tests — L3 长期借款公式引擎
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 2.1
 *
 * 已知值验证，互补 PBT 测试。
 * 覆盖 Properties P1, P2, P6, P8 的具体场景。
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcCreditDiff,
  calcPledgeRatio,
} from '../useL3FormulaEngine'

describe('useL3FormulaEngine', () => {
  // ── calcAuditedAmount (P1) ──────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('审定数 = 未审数 + AJE + RJE', () => {
      expect(calcAuditedAmount(1000, 50, -30)).toBe(1020)
    })

    it('无调整时审定数等于未审数', () => {
      expect(calcAuditedAmount(5000, 0, 0)).toBe(5000)
    })

    it('负数场景正确计算', () => {
      expect(calcAuditedAmount(100, -200, 50)).toBe(-50)
    })

    it('全零返回0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })
  })

  // ── calcLiabilityEndBalance（负债类！）(P2) ─────────────────────────────

  describe('calcLiabilityEndBalance', () => {
    it('负债类：期末 = 期初 + 贷方(借入) - 借方(归还)', () => {
      // 期初1000 + 借入500 - 归还200 = 1300
      expect(calcLiabilityEndBalance(1000, 500, 200)).toBe(1300)
    })

    it('全额归还后期末为0', () => {
      expect(calcLiabilityEndBalance(1000, 0, 1000)).toBe(0)
    })

    it('归还超过期初+借入时期末为负（异常场景）', () => {
      expect(calcLiabilityEndBalance(100, 50, 200)).toBe(-50)
    })

    it('仅有借入时期末增加', () => {
      expect(calcLiabilityEndBalance(1000, 2000, 0)).toBe(3000)
    })

    it('全零返回0', () => {
      expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
    })
  })

  // ── calcSubtotal (P8) ──────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('多个金额求和', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })

    it('空数组返回0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素返回自身', () => {
      expect(calcSubtotal([999])).toBe(999)
    })

    it('含负数正确求和', () => {
      expect(calcSubtotal([100, -50, 200])).toBe(250)
    })
  })

  // ── calcCreditDiff ─────────────────────────────────────────────────────

  describe('calcCreditDiff', () => {
    it('差异 = 征信余额 - 账面余额', () => {
      expect(calcCreditDiff(1000, 800)).toBe(200)
    })

    it('一致时差异为0', () => {
      expect(calcCreditDiff(5000, 5000)).toBe(0)
    })

    it('账面大于征信时差异为负', () => {
      expect(calcCreditDiff(800, 1000)).toBe(-200)
    })
  })

  // ── calcPledgeRatio (P6) ───────────────────────────────────────────────

  describe('calcPledgeRatio', () => {
    it('担保比例 = 贷款额/资产价值×100', () => {
      // 500万贷款 / 1000万资产 = 50%
      expect(calcPledgeRatio(500, 1000)).toBe(50)
    })

    it('贷款超过资产价值时比例>100%', () => {
      expect(calcPledgeRatio(1500, 1000)).toBe(150)
    })

    it('资产价值为0时返回0（除零保护）', () => {
      expect(calcPledgeRatio(1000, 0)).toBe(0)
    })

    it('贷款为0时比例为0', () => {
      expect(calcPledgeRatio(0, 1000)).toBe(0)
    })
  })
})
