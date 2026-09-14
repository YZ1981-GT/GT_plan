/**
 * useL1FormulaEngine 单元测试
 * 科目：2001 短期借款（贷方/负债类）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcCreditDiff,
  calcPledgeRatio,
  calcCreditRollForward,
} from '../useL1FormulaEngine'

describe('useL1FormulaEngine', () => {
  // ─── calcAuditedAmount ──────────────────────────────────
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
  })

  // ─── calcLiabilityEndBalance（负债类！） ─────────────────
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
  })

  // ─── calcSubtotal ──────────────────────────────────────
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

  // ─── calcCreditDiff ────────────────────────────────────
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

  // ─── calcPledgeRatio ───────────────────────────────────
  describe('calcPledgeRatio', () => {
    it('担保比例 = 贷款额/资产净值×100', () => {
      // 500万贷款 / 1000万资产 = 50%
      expect(calcPledgeRatio(500, 1000)).toBe(50)
    })

    it('贷款超过资产净值时比例>100%', () => {
      expect(calcPledgeRatio(1500, 1000)).toBe(150)
    })

    it('资产净值为0时返回0（除零保护）', () => {
      expect(calcPledgeRatio(1000, 0)).toBe(0)
    })

    it('贷款为0时比例为0', () => {
      expect(calcPledgeRatio(0, 1000)).toBe(0)
    })
  })

  // ─── calcCreditRollForward ─────────────────────────────
  describe('calcCreditRollForward', () => {
    it('倒轧余额 = 查询日余额 + 增加 - 减少', () => {
      expect(calcCreditRollForward(1000, 200, 100)).toBe(1100)
    })

    it('无增减时余额不变', () => {
      expect(calcCreditRollForward(5000, 0, 0)).toBe(5000)
    })

    it('减少大于增加时余额下降', () => {
      expect(calcCreditRollForward(1000, 100, 500)).toBe(600)
    })
  })
})
