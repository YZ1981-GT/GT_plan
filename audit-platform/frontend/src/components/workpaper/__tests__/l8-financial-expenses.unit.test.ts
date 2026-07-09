/**
 * 单元测试 — useL8FormulaEngine + useL8InterestEngine + useL8CutoffEngine
 *
 * 覆盖：
 * 1. useL8FormulaEngine: calcAuditedAmount, calcOccurrence, calcNetFinanceExpense,
 *    calcChangeRate, calcSubtotal, calcChangeAmount, isChangeRateExceeding,
 *    validateAdjudicationVsDetail, parseNum
 * 2. useL8InterestEngine: aggregateInterest, calcInterestDiff, calcDeductibleInterest,
 *    calcExcessInterest, hasExcessInterest, isInterestDiffExceeding
 * 3. useL8CutoffEngine: isCrossPeriod, extractCutoffWindow, extractCrossPeriodEntries,
 *    calcCrossPeriodTotal, calcCrossPeriodRate
 *
 * Spec: .kiro/specs/l8-financial-expenses/ Task 7.1
 * Requirements: P1-P7
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcOccurrence,
  calcNetFinanceExpense,
  calcChangeRate,
  calcSubtotal,
  calcChangeAmount,
  isChangeRateExceeding,
  validateAdjudicationVsDetail,
} from '../composables/useL8FormulaEngine'
import {
  aggregateInterest,
  calcInterestDiff,
  calcDeductibleInterest,
  calcExcessInterest,
  hasExcessInterest,
  isInterestDiffExceeding,
} from '../composables/useL8InterestEngine'
import {
  isCrossPeriod,
  extractCutoffWindow,
  extractCrossPeriodEntries,
  calcCrossPeriodTotal,
  calcCrossPeriodRate,
  type LedgerEntry,
} from '../composables/useL8CutoffEngine'


// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: useL8FormulaEngine
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL8FormulaEngine — 损益类发生额公式引擎', () => {
  // ─── parseNum ──────────────────────────────────────────────────────────────

  describe('parseNum', () => {
    it('正常数字直接返回', () => {
      expect(parseNum(100)).toBe(100)
      expect(parseNum(-50.5)).toBe(-50.5)
      expect(parseNum(0)).toBe(0)
    })

    it('字符串数字正确解析', () => {
      expect(parseNum('123.45')).toBe(123.45)
      expect(parseNum('-99')).toBe(-99)
      expect(parseNum('0')).toBe(0)
    })

    it('null/undefined/空字符串→0', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
    })

    it('NaN/Infinity→0', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })

    it('非数字字符串→0', () => {
      expect(parseNum('abc')).toBe(0)
      expect(parseNum('N/A')).toBe(0)
    })
  })


  // ─── calcAuditedAmount ────────────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('基本公式：u + a + r', () => {
      expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
      expect(calcAuditedAmount(5000000, -100000, 0)).toBe(4900000)
    })

    it('全零→0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负数（费用冲回）', () => {
      expect(calcAuditedAmount(500, -600, 0)).toBe(-100)
    })

    it('大金额', () => {
      expect(calcAuditedAmount(100_000_000, 5_000_000, -2_000_000)).toBe(103_000_000)
    })
  })

  // ─── calcOccurrence（损益类核心！借-贷） ──────────────────────────────────

  describe('calcOccurrence（损益类发生额 = 借方-贷方）', () => {
    it('借方>贷方 → 正值（费用净增加）', () => {
      expect(calcOccurrence(500000, 100000)).toBe(400000)
    })

    it('借方=贷方 → 0', () => {
      expect(calcOccurrence(300000, 300000)).toBe(0)
    })

    it('借方<贷方 → 负值（费用净冲回）', () => {
      expect(calcOccurrence(100000, 500000)).toBe(-400000)
    })

    it('零值', () => {
      expect(calcOccurrence(0, 0)).toBe(0)
      expect(calcOccurrence(0, 100)).toBe(-100)
      expect(calcOccurrence(100, 0)).toBe(100)
    })
  })


  // ─── calcNetFinanceExpense ─────────────────────────────────────────────────

  describe('calcNetFinanceExpense', () => {
    it('标准公式：ie - ii + fx + fee + other', () => {
      // 利息支出100 - 利息收入20 + 汇兑损失30 + 手续费10 + 其他5 = 125
      expect(calcNetFinanceExpense(100, 20, 30, 10, 5)).toBe(125)
    })

    it('利息收入为减项', () => {
      expect(calcNetFinanceExpense(0, 500, 0, 0, 0)).toBe(-500)
    })

    it('全零', () => {
      expect(calcNetFinanceExpense(0, 0, 0, 0, 0)).toBe(0)
    })

    it('负数汇兑（收益）', () => {
      expect(calcNetFinanceExpense(200, 50, -30, 10, 0)).toBe(130)
    })
  })

  // ─── calcChangeRate ───────────────────────────────────────────────────────

  describe('calcChangeRate', () => {
    it('正常变动率: (cur-prior)/prior×100', () => {
      expect(calcChangeRate(120, 100)).toBeCloseTo(20, 5)
      expect(calcChangeRate(50, 100)).toBeCloseTo(-50, 5)
    })

    it('prior=0 → N/A', () => {
      expect(calcChangeRate(100, 0)).toBe('N/A')
      expect(calcChangeRate(0, 0)).toBe('N/A')
    })

    it('cur=prior → 0%', () => {
      expect(calcChangeRate(500, 500)).toBeCloseTo(0, 5)
    })

    it('负prior', () => {
      // current=50, prior=-100 → (50-(-100))/(-100)×100 = -150
      expect(calcChangeRate(50, -100)).toBeCloseTo(-150, 5)
    })
  })


  // ─── calcSubtotal ─────────────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('正常求和', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })

    it('含负数', () => {
      expect(calcSubtotal([100, -50, 200])).toBe(250)
    })

    it('空数组→0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素', () => {
      expect(calcSubtotal([999])).toBe(999)
    })

    it('非数组→0', () => {
      expect(calcSubtotal(null as any)).toBe(0)
      expect(calcSubtotal(undefined as any)).toBe(0)
    })
  })

  // ─── calcChangeAmount ─────────────────────────────────────────────────────

  describe('calcChangeAmount', () => {
    it('正常变动额：current - prior', () => {
      expect(calcChangeAmount(1200, 1000)).toBe(200)
      expect(calcChangeAmount(800, 1000)).toBe(-200)
    })

    it('相等→0', () => {
      expect(calcChangeAmount(500, 500)).toBe(0)
    })

    it('零值', () => {
      expect(calcChangeAmount(0, 0)).toBe(0)
      expect(calcChangeAmount(100, 0)).toBe(100)
    })
  })


  // ─── isChangeRateExceeding ────────────────────────────────────────────────

  describe('isChangeRateExceeding', () => {
    it('超过阈值→true', () => {
      expect(isChangeRateExceeding(25, 20)).toBe(true)
      expect(isChangeRateExceeding(-30, 20)).toBe(true)
    })

    it('未超阈值→false', () => {
      expect(isChangeRateExceeding(15, 20)).toBe(false)
      expect(isChangeRateExceeding(-10, 20)).toBe(false)
    })

    it('等于阈值→false', () => {
      expect(isChangeRateExceeding(20, 20)).toBe(false)
    })

    it('N/A → false', () => {
      expect(isChangeRateExceeding('N/A', 20)).toBe(false)
    })
  })

  // ─── validateAdjudicationVsDetail ─────────────────────────────────────────

  describe('validateAdjudicationVsDetail', () => {
    it('匹配（差额<0.01）→isMatch=true', () => {
      const result = validateAdjudicationVsDetail(1000000, 1000000)
      expect(result.isMatch).toBe(true)
      expect(result.diff).toBeCloseTo(0, 2)
    })

    it('审定>明细→正差额', () => {
      const result = validateAdjudicationVsDetail(1500000, 1000000)
      expect(result.isMatch).toBe(false)
      expect(result.diff).toBe(500000)
    })

    it('审定<明细→负差额', () => {
      const result = validateAdjudicationVsDetail(800000, 1000000)
      expect(result.isMatch).toBe(false)
      expect(result.diff).toBe(-200000)
    })

    it('两侧为0→匹配', () => {
      const result = validateAdjudicationVsDetail(0, 0)
      expect(result.isMatch).toBe(true)
      expect(result.diff).toBe(0)
    })
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: useL8InterestEngine
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL8InterestEngine — 利息支出测算引擎', () => {
  // ─── aggregateInterest ────────────────────────────────────────────────────

  describe('aggregateInterest', () => {
    it('汇总L1/L3/L4/L5利息', () => {
      expect(aggregateInterest(100000, 200000, 50000, 30000)).toBe(380000)
    })

    it('全零→0', () => {
      expect(aggregateInterest(0, 0, 0, 0)).toBe(0)
    })

    it('部分为零', () => {
      expect(aggregateInterest(100000, 0, 0, 50000)).toBe(150000)
    })

    it('负值（利息冲回）', () => {
      expect(aggregateInterest(100000, -20000, 50000, 0)).toBe(130000)
    })
  })

  // ─── calcInterestDiff ─────────────────────────────────────────────────────

  describe('calcInterestDiff', () => {
    it('测算>账面 → 正差异', () => {
      expect(calcInterestDiff(500000, 450000)).toBe(50000)
    })

    it('测算<账面 → 负差异', () => {
      expect(calcInterestDiff(400000, 500000)).toBe(-100000)
    })

    it('相等→0', () => {
      expect(calcInterestDiff(300000, 300000)).toBe(0)
    })

    it('零值', () => {
      expect(calcInterestDiff(0, 0)).toBe(0)
      expect(calcInterestDiff(100000, 0)).toBe(100000)
    })
  })


  // ─── calcDeductibleInterest ───────────────────────────────────────────────

  describe('calcDeductibleInterest', () => {
    it('标准计算：本金×基准利率×天数/360', () => {
      // 1000000 × 0.0435 × 365 / 360 = 44104.17
      const result = calcDeductibleInterest(1000000, 0.0435, 365)
      expect(result).toBeCloseTo(44104.17, 0)
    })

    it('天数=0 → 0', () => {
      expect(calcDeductibleInterest(1000000, 0.05, 0)).toBe(0)
    })

    it('本金=0 → 0', () => {
      expect(calcDeductibleInterest(0, 0.05, 180)).toBe(0)
    })

    it('半年（180天）', () => {
      // 500000 × 0.04 × 180 / 360 = 10000
      expect(calcDeductibleInterest(500000, 0.04, 180)).toBeCloseTo(10000, 2)
    })

    it('1天', () => {
      // 1000000 × 0.05 × 1 / 360 = 138.89
      expect(calcDeductibleInterest(1000000, 0.05, 1)).toBeCloseTo(138.89, 1)
    })
  })

  // ─── calcExcessInterest ───────────────────────────────────────────────────

  describe('calcExcessInterest', () => {
    it('超标：账载 > 可扣除', () => {
      expect(calcExcessInterest(50000, 30000)).toBe(20000)
    })

    it('未超标：账载 ≤ 可扣除', () => {
      expect(calcExcessInterest(30000, 50000)).toBe(-20000)
    })

    it('相等→0', () => {
      expect(calcExcessInterest(40000, 40000)).toBe(0)
    })

    it('零值', () => {
      expect(calcExcessInterest(0, 0)).toBe(0)
    })
  })


  // ─── hasExcessInterest ────────────────────────────────────────────────────

  describe('hasExcessInterest', () => {
    it('正值→true（需税务调整）', () => {
      expect(hasExcessInterest(10000)).toBe(true)
      expect(hasExcessInterest(0.01)).toBe(true)
    })

    it('零→false', () => {
      expect(hasExcessInterest(0)).toBe(false)
    })

    it('负值→false', () => {
      expect(hasExcessInterest(-5000)).toBe(false)
    })
  })

  // ─── isInterestDiffExceeding ──────────────────────────────────────────────

  describe('isInterestDiffExceeding', () => {
    it('|diff|>阈值→true', () => {
      expect(isInterestDiffExceeding(150, 100)).toBe(true)
      expect(isInterestDiffExceeding(-200, 100)).toBe(true)
    })

    it('|diff|≤阈值→false', () => {
      expect(isInterestDiffExceeding(50, 100)).toBe(false)
      expect(isInterestDiffExceeding(-80, 100)).toBe(false)
    })

    it('等于阈值→false', () => {
      expect(isInterestDiffExceeding(100, 100)).toBe(false)
    })

    it('零差异→false', () => {
      expect(isInterestDiffExceeding(0, 100)).toBe(false)
    })
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: useL8CutoffEngine
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL8CutoffEngine — 截止测试引擎', () => {
  // ─── Fixtures ─────────────────────────────────────────────────────────────

  const sampleLedger: LedgerEntry[] = [
    { voucherNo: 'V001', date: '2024-12-28', summary: '利息支出', amount: 50000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '2001' },
    { voucherNo: 'V002', date: '2024-12-30', summary: '手续费', amount: 2000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '1002' },
    { voucherNo: 'V003', date: '2024-12-31', summary: '利息计提', amount: 80000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '2211' },
    { voucherNo: 'V004', date: '2025-01-02', summary: '12月利息后入账', amount: 30000, attributionPeriod: '2024-12', bookingPeriod: '2025-01', counterAccount: '2001' },
    { voucherNo: 'V005', date: '2025-01-03', summary: '1月手续费', amount: 1500, attributionPeriod: '2025-01', bookingPeriod: '2025-01', counterAccount: '1002' },
    { voucherNo: 'V006', date: '2025-01-10', summary: '1月远期利息', amount: 60000, attributionPeriod: '2025-01', bookingPeriod: '2025-01', counterAccount: '2001' },
    { voucherNo: 'V007', date: '2024-12-20', summary: '12月初利息', amount: 45000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '2001' },
  ]

  // ─── isCrossPeriod ────────────────────────────────────────────────────────

  describe('isCrossPeriod', () => {
    it('不同期间→跨期(true)', () => {
      expect(isCrossPeriod('2024-12', '2025-01')).toBe(true)
    })

    it('相同期间→不跨期(false)', () => {
      expect(isCrossPeriod('2024-12', '2024-12')).toBe(false)
    })

    it('空attributionPeriod→false', () => {
      expect(isCrossPeriod('', '2024-12')).toBe(false)
    })

    it('空bookingPeriod→false', () => {
      expect(isCrossPeriod('2024-12', '')).toBe(false)
    })

    it('两者均空→false', () => {
      expect(isCrossPeriod('', '')).toBe(false)
    })

    it('空格trim', () => {
      expect(isCrossPeriod(' 2024-12 ', '2024-12')).toBe(false)
      expect(isCrossPeriod('2024-12', ' 2025-01 ')).toBe(true)
    })
  })


  // ─── extractCutoffWindow ──────────────────────────────────────────────────

  describe('extractCutoffWindow', () => {
    it('±5天窗口提取正确条目', () => {
      const result = extractCutoffWindow(sampleLedger, '2024-12-31', 5)
      // 12/26~01/05 范围内: V001(12/28), V002(12/30), V003(12/31), V004(01/02), V005(01/03)
      expect(result.length).toBe(5)
      expect(result.map(e => e.voucherNo)).toContain('V001')
      expect(result.map(e => e.voucherNo)).toContain('V004')
      expect(result.map(e => e.voucherNo)).toContain('V005')
      // V006(01/10) 和 V007(12/20) 应被排除
      expect(result.map(e => e.voucherNo)).not.toContain('V006')
      expect(result.map(e => e.voucherNo)).not.toContain('V007')
    })

    it('窗口=0 → 只取报告日当天', () => {
      const result = extractCutoffWindow(sampleLedger, '2024-12-31', 0)
      expect(result.length).toBe(1)
      expect(result[0].voucherNo).toBe('V003')
    })

    it('空ledger→空结果', () => {
      expect(extractCutoffWindow([], '2024-12-31', 5)).toEqual([])
    })

    it('无效日期→空结果', () => {
      expect(extractCutoffWindow(sampleLedger, '', 5)).toEqual([])
      expect(extractCutoffWindow(sampleLedger, 'invalid', 5)).toEqual([])
    })

    it('负天数→空结果', () => {
      expect(extractCutoffWindow(sampleLedger, '2024-12-31', -1)).toEqual([])
    })

    it('null ledger→空结果', () => {
      expect(extractCutoffWindow(null as any, '2024-12-31', 5)).toEqual([])
    })
  })


  // ─── extractCrossPeriodEntries ─────────────────────────────────────────────

  describe('extractCrossPeriodEntries', () => {
    it('窗口内筛选跨期条目', () => {
      const result = extractCrossPeriodEntries(sampleLedger, '2024-12-31', 5)
      // V004: attributionPeriod=2024-12, bookingPeriod=2025-01 → 跨期！
      expect(result.length).toBe(1)
      expect(result[0].voucherNo).toBe('V004')
    })

    it('无跨期条目→空', () => {
      const noCorssLedger: LedgerEntry[] = [
        { voucherNo: 'V01', date: '2024-12-31', summary: 'test', amount: 100, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '1001' },
      ]
      const result = extractCrossPeriodEntries(noCorssLedger, '2024-12-31', 5)
      expect(result).toEqual([])
    })

    it('空ledger→空', () => {
      expect(extractCrossPeriodEntries([], '2024-12-31', 5)).toEqual([])
    })
  })

  // ─── calcCrossPeriodTotal ─────────────────────────────────────────────────

  describe('calcCrossPeriodTotal', () => {
    it('累加跨期金额', () => {
      const entries: LedgerEntry[] = [
        { voucherNo: 'V1', date: '2025-01-02', summary: '', amount: 30000, attributionPeriod: '2024-12', bookingPeriod: '2025-01', counterAccount: '' },
        { voucherNo: 'V2', date: '2025-01-03', summary: '', amount: 20000, attributionPeriod: '2024-12', bookingPeriod: '2025-01', counterAccount: '' },
      ]
      expect(calcCrossPeriodTotal(entries)).toBe(50000)
    })

    it('空数组→0', () => {
      expect(calcCrossPeriodTotal([])).toBe(0)
    })

    it('非数组→0', () => {
      expect(calcCrossPeriodTotal(null as any)).toBe(0)
    })
  })

  // ─── calcCrossPeriodRate ──────────────────────────────────────────────────

  describe('calcCrossPeriodRate', () => {
    it('标准跨期率：crossCount/totalCount×100', () => {
      expect(calcCrossPeriodRate(2, 10)).toBeCloseTo(20, 5)
      expect(calcCrossPeriodRate(1, 5)).toBeCloseTo(20, 5)
    })

    it('totalCount=0→0', () => {
      expect(calcCrossPeriodRate(0, 0)).toBe(0)
      expect(calcCrossPeriodRate(5, 0)).toBe(0)
    })

    it('crossCount=0→0%', () => {
      expect(calcCrossPeriodRate(0, 10)).toBe(0)
    })

    it('100%跨期', () => {
      expect(calcCrossPeriodRate(5, 5)).toBeCloseTo(100, 5)
    })
  })
})
