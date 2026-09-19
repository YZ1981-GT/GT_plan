/**
 * L3 长期借款 三引擎单元测试
 * - useL3FormulaEngine: 负债类方向公式
 * - useL3InterestEngine: 利息测算 (365天制)
 * - useL3ReclassEngine: 一年内到期重分类
 *
 * Requirements: P1-P8
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcCreditDiff,
  calcPledgeRatio,
} from '../useL3FormulaEngine'
import {
  calcInterest,
  calcOverdueDays,
  calcInterestDiff,
} from '../useL3InterestEngine'
import {
  calcCurrentPortion,
  buildReclassEntry,
} from '../useL3ReclassEngine'

// ═══════════════════════════════════════════════════════════════
// useL3FormulaEngine
// ═══════════════════════════════════════════════════════════════

describe('useL3FormulaEngine', () => {
  // ─── P1: calcAuditedAmount ─────────────────────────────────
  describe('calcAuditedAmount (P1)', () => {
    it('审定数 = 未审数 + AJE + RJE', () => {
      expect(calcAuditedAmount(10000, 500, -200)).toBe(10300)
    })

    it('无调整时审定数等于未审数', () => {
      expect(calcAuditedAmount(8000, 0, 0)).toBe(8000)
    })

    it('负数调整正确计算', () => {
      expect(calcAuditedAmount(1000, -1500, 200)).toBe(-300)
    })
  })

  // ─── P2: calcLiabilityEndBalance（负债类贷方！） ────────────
  describe('calcLiabilityEndBalance (P2)', () => {
    it('负债类：期末 = 期初 + 贷方(借入) - 借方(归还)', () => {
      // 期初5000 + 借入3000 - 归还1000 = 7000
      expect(calcLiabilityEndBalance(5000, 3000, 1000)).toBe(7000)
    })

    it('全额归还后期末为0', () => {
      expect(calcLiabilityEndBalance(2000, 0, 2000)).toBe(0)
    })

    it('仅有借入时期末增加', () => {
      expect(calcLiabilityEndBalance(1000, 5000, 0)).toBe(6000)
    })

    it('归还大于期初+借入时期末为负（异常但公式正确）', () => {
      expect(calcLiabilityEndBalance(100, 50, 300)).toBe(-150)
    })
  })

  // ─── P8: calcSubtotal ─────────────────────────────────────
  describe('calcSubtotal (P8)', () => {
    it('多金额求和', () => {
      expect(calcSubtotal([1000, 2000, 3000, 500])).toBe(6500)
    })

    it('空数组返回0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素返回自身', () => {
      expect(calcSubtotal([7777])).toBe(7777)
    })

    it('含负数正确求和', () => {
      expect(calcSubtotal([500, -200, 300, -100])).toBe(500)
    })
  })

  // ─── calcCreditDiff ───────────────────────────────────────
  describe('calcCreditDiff', () => {
    it('差异 = 征信余额 - 账面余额', () => {
      expect(calcCreditDiff(5000, 4500)).toBe(500)
    })

    it('一致时差异为0', () => {
      expect(calcCreditDiff(3000, 3000)).toBe(0)
    })

    it('账面大于征信时差异为负', () => {
      expect(calcCreditDiff(2000, 3000)).toBe(-1000)
    })
  })

  // ─── P6: calcPledgeRatio ──────────────────────────────────
  describe('calcPledgeRatio (P6)', () => {
    it('担保比例 = 担保借款/资产账面价值×100', () => {
      // 800万贷款 / 2000万资产 = 40%
      expect(calcPledgeRatio(800, 2000)).toBe(40)
    })

    it('贷款超过资产时比例>100%', () => {
      expect(calcPledgeRatio(1500, 1000)).toBe(150)
    })

    it('资产账面价值为0时返回0（除零保护）', () => {
      expect(calcPledgeRatio(5000, 0)).toBe(0)
    })

    it('贷款为0时比例为0', () => {
      expect(calcPledgeRatio(0, 8000)).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════
// useL3InterestEngine
// ═══════════════════════════════════════════════════════════════

describe('useL3InterestEngine', () => {
  // ─── P3: calcInterest ─────────────────────────────────────
  describe('calcInterest (P3)', () => {
    it('利息 = 本金 × 年利率 × 天数 / 365', () => {
      // 1000000 * 0.05 * 90 / 365 ≈ 12328.77
      const result = calcInterest(1000000, 0.05, 90)
      expect(result).toBeCloseTo(1000000 * 0.05 * 90 / 365, 5)
    })

    it('整年计息', () => {
      // 本金100万, 利率5%, 365天 = 50000
      expect(calcInterest(1000000, 0.05, 365)).toBeCloseTo(50000, 5)
    })
  })

  // ─── P4: calcInterest boundary ────────────────────────────
  describe('calcInterest boundary (P4)', () => {
    it('days=0 → 利息为0', () => {
      expect(calcInterest(1000000, 0.05, 0)).toBe(0)
    })

    it('rate=0 → 利息为0', () => {
      expect(calcInterest(1000000, 0, 90)).toBe(0)
    })

    it('principal=0 → 利息为0', () => {
      expect(calcInterest(0, 0.05, 90)).toBe(0)
    })

    it('days<0 → 利息为0（无效区间）', () => {
      expect(calcInterest(1000000, 0.05, -10)).toBe(0)
    })
  })

  // ─── P5: calcOverdueDays ──────────────────────────────────
  describe('calcOverdueDays (P5)', () => {
    it('逾期天数 = 报告日 - 到期日', () => {
      // 到期2024-06-30, 报告2024-12-31 → 逾期184天
      expect(calcOverdueDays('2024-06-30', '2024-12-31')).toBe(184)
    })

    it('未到期时返回负数', () => {
      // 到期2025-06-30, 报告2024-12-31 → 未到期 -181天
      expect(calcOverdueDays('2025-06-30', '2024-12-31')).toBe(-181)
    })

    it('当天到期返回0', () => {
      expect(calcOverdueDays('2024-12-31', '2024-12-31')).toBe(0)
    })

    it('无效日期返回0', () => {
      expect(calcOverdueDays('', '2024-12-31')).toBe(0)
      expect(calcOverdueDays('2024-12-31', '')).toBe(0)
    })
  })

  // ─── calcInterestDiff ─────────────────────────────────────
  describe('calcInterestDiff', () => {
    it('差异 = 测算利息 - 账载利息', () => {
      expect(calcInterestDiff(12500, 12000)).toBe(500)
    })

    it('账载偏高时差异为负', () => {
      expect(calcInterestDiff(10000, 11000)).toBe(-1000)
    })

    it('完全一致时差异为0', () => {
      expect(calcInterestDiff(5000, 5000)).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════
// useL3ReclassEngine
// ═══════════════════════════════════════════════════════════════

describe('useL3ReclassEngine', () => {
  // ─── P7: calcCurrentPortion ───────────────────────────────
  describe('calcCurrentPortion (P7)', () => {
    it('到期日在报告日+1年内 → 全额重分类', () => {
      // 报告日2024-12-31, 到期日2025-06-30 (半年后) → 全额
      expect(calcCurrentPortion('2025-06-30', '2024-12-31', 5000000)).toBe(5000000)
    })

    it('到期日恰好等于报告日+1年 → 全额重分类（含边界）', () => {
      // 报告日2024-12-31, 到期日2025-12-31 → 恰好1年，需重分类
      expect(calcCurrentPortion('2025-12-31', '2024-12-31', 3000000)).toBe(3000000)
    })

    it('到期日超过报告日+1年 → 不重分类返回0', () => {
      // 报告日2024-12-31, 到期日2026-06-30 (1.5年后) → 0
      expect(calcCurrentPortion('2026-06-30', '2024-12-31', 5000000)).toBe(0)
    })

    it('已逾期（到期日早于报告日）→ 仍需重分类', () => {
      // 报告日2024-12-31, 到期日2024-06-30 (已逾期半年) → 全额
      expect(calcCurrentPortion('2024-06-30', '2024-12-31', 2000000)).toBe(2000000)
    })

    it('amount<=0 → 返回0', () => {
      expect(calcCurrentPortion('2025-06-30', '2024-12-31', 0)).toBe(0)
      expect(calcCurrentPortion('2025-06-30', '2024-12-31', -100)).toBe(0)
    })

    it('无效日期 → 返回0', () => {
      expect(calcCurrentPortion('', '2024-12-31', 5000000)).toBe(0)
      expect(calcCurrentPortion('2025-06-30', '', 5000000)).toBe(0)
    })
  })

  // ─── buildReclassEntry ────────────────────────────────────
  describe('buildReclassEntry', () => {
    it('生成正确的借贷分录结构', () => {
      const entry = buildReclassEntry(3000000)
      expect(entry.description).toBe('一年内到期的长期借款重分类')
      expect(entry.debit.account).toBe('长期借款')
      expect(entry.debit.accountCode).toBe('2501')
      expect(entry.debit.amount).toBe(3000000)
      expect(entry.credit.account).toBe('一年内到期的非流动负债')
      expect(entry.credit.accountCode).toBe('2801')
      expect(entry.credit.amount).toBe(3000000)
    })

    it('借贷金额相等（借贷平衡）', () => {
      const entry = buildReclassEntry(1500000)
      expect(entry.debit.amount).toBe(entry.credit.amount)
    })

    it('amount<=0 → 金额为0的分录（防御性abs处理）', () => {
      const entry = buildReclassEntry(0)
      expect(entry.debit.amount).toBe(0)
      expect(entry.credit.amount).toBe(0)
    })

    it('负数金额使用绝对值（防御性）', () => {
      const entry = buildReclassEntry(-500000)
      expect(entry.debit.amount).toBe(500000)
      expect(entry.credit.amount).toBe(500000)
    })
  })
})
