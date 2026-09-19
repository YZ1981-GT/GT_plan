/**
 * useD4FormulaEngine 单元测试
 *
 * 覆盖所有纯函数的核心逻辑和边界条件。
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcMonthlyTotal,
  calcAuditedWithAdj,
  calcChangeRate,
  calcChangeAmount,
  calcSubtotal,
  calcGrossMarginRate,
  calcProportion,
  calcPriceDiffRate,
  isChangeRateExceeding,
  calcAnomalyRate,
  calcCoverageRate,
  isCrossPeriod,
  isCrossPeriodForward,
  isCrossPeriodBackward,
  calcCrossPeriodDays,
  isSuspiciousFundFlow,
  isIpoGroupVisible,
  D4_10_TOTAL_AMOUNT_PRESET,
  parseWpFormulaRef,
  resolveD42PeriodUnadjustedTotal,
  resolvePresetOrOverride,
} from '../useD4FormulaEngine'

describe('useD4FormulaEngine', () => {
  // ─── parseNum ─────────────────────────────────────────────────────────────

  describe('parseNum', () => {
    it('returns 0 for null', () => {
      expect(parseNum(null)).toBe(0)
    })

    it('returns 0 for undefined', () => {
      expect(parseNum(undefined)).toBe(0)
    })

    it('returns 0 for empty string', () => {
      expect(parseNum('')).toBe(0)
    })

    it('returns 0 for NaN string', () => {
      expect(parseNum('abc')).toBe(0)
    })

    it('returns 0 for Infinity', () => {
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })

    it('parses numeric strings', () => {
      expect(parseNum('123.45')).toBe(123.45)
      expect(parseNum('-100')).toBe(-100)
    })

    it('passes through numbers', () => {
      expect(parseNum(42)).toBe(42)
      expect(parseNum(-3.14)).toBe(-3.14)
      expect(parseNum(0)).toBe(0)
    })
  })

  // ─── calcAuditedAmount ────────────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('sums unadjusted + aje + rje', () => {
      expect(calcAuditedAmount(1000, 50, -30)).toBe(1020)
    })

    it('handles all zeros', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('handles negative values', () => {
      expect(calcAuditedAmount(-100, -50, 30)).toBe(-120)
    })
  })

  // ─── calcMonthlyTotal ─────────────────────────────────────────────────────

  describe('calcMonthlyTotal', () => {
    it('sums 12 months', () => {
      const months = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200]
      expect(calcMonthlyTotal(months)).toBe(7800)
    })

    it('handles empty array', () => {
      expect(calcMonthlyTotal([])).toBe(0)
    })

    it('handles negative values', () => {
      expect(calcMonthlyTotal([100, -50, 200])).toBe(250)
    })
  })

  // ─── calcAuditedWithAdj ───────────────────────────────────────────────────

  describe('calcAuditedWithAdj', () => {
    it('adds unadjusted total and adjustment', () => {
      expect(calcAuditedWithAdj(10000, 500)).toBe(10500)
    })

    it('handles negative adjustment', () => {
      expect(calcAuditedWithAdj(10000, -200)).toBe(9800)
    })
  })

  // ─── calcChangeRate ───────────────────────────────────────────────────────

  describe('calcChangeRate', () => {
    it('returns empty string when both are 0', () => {
      expect(calcChangeRate(0, 0)).toBe('')
    })

    it('returns N/A when prior is 0 and current is not', () => {
      expect(calcChangeRate(100, 0)).toBe('N/A')
    })

    it('calculates rate correctly', () => {
      expect(calcChangeRate(120, 100)).toBeCloseTo(0.2)
    })

    it('calculates negative change', () => {
      expect(calcChangeRate(80, 100)).toBeCloseTo(-0.2)
    })

    it('handles current equals prior', () => {
      expect(calcChangeRate(100, 100)).toBe(0)
    })
  })

  // ─── calcChangeAmount ─────────────────────────────────────────────────────

  describe('calcChangeAmount', () => {
    it('calculates difference', () => {
      expect(calcChangeAmount(150, 100)).toBe(50)
    })

    it('handles negative difference', () => {
      expect(calcChangeAmount(80, 100)).toBe(-20)
    })
  })

  // ─── calcSubtotal ─────────────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('sums values', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })

    it('handles empty array', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('handles single value', () => {
      expect(calcSubtotal([42])).toBe(42)
    })
  })

  // ─── calcGrossMarginRate ──────────────────────────────────────────────────

  describe('calcGrossMarginRate', () => {
    it('calculates margin rate', () => {
      expect(calcGrossMarginRate(1000, 600)).toBeCloseTo(0.4)
    })

    it('returns 0 when revenue is 0', () => {
      expect(calcGrossMarginRate(0, 100)).toBe(0)
    })

    it('handles cost > revenue (negative margin)', () => {
      expect(calcGrossMarginRate(100, 150)).toBeCloseTo(-0.5)
    })
  })

  // ─── calcProportion ───────────────────────────────────────────────────────

  describe('calcProportion', () => {
    it('calculates proportion as percentage', () => {
      expect(calcProportion(250, 1000)).toBe(25)
    })

    it('returns 0 when total is 0', () => {
      expect(calcProportion(100, 0)).toBe(0)
    })

    it('handles item equal to total', () => {
      expect(calcProportion(500, 500)).toBe(100)
    })
  })

  // ─── calcPriceDiffRate ────────────────────────────────────────────────────

  describe('calcPriceDiffRate', () => {
    it('calculates price difference rate as percentage', () => {
      expect(calcPriceDiffRate(110, 100)).toBeCloseTo(10)
    })

    it('returns 0 when nonRelatedPrice is 0', () => {
      expect(calcPriceDiffRate(100, 0)).toBe(0)
    })

    it('handles related < nonRelated (negative rate)', () => {
      expect(calcPriceDiffRate(90, 100)).toBeCloseTo(-10)
    })
  })

  // ─── isChangeRateExceeding ────────────────────────────────────────────────

  describe('isChangeRateExceeding', () => {
    it('returns false for empty string', () => {
      expect(isChangeRateExceeding('', 0.3)).toBe(false)
    })

    it('returns false for N/A', () => {
      expect(isChangeRateExceeding('N/A', 0.3)).toBe(false)
    })

    it('returns true when abs(rate) > threshold', () => {
      expect(isChangeRateExceeding(0.5, 0.3)).toBe(true)
      expect(isChangeRateExceeding(-0.5, 0.3)).toBe(true)
    })

    it('returns false when abs(rate) <= threshold', () => {
      expect(isChangeRateExceeding(0.2, 0.3)).toBe(false)
      expect(isChangeRateExceeding(0.3, 0.3)).toBe(false)
    })
  })

  // ─── calcAnomalyRate ──────────────────────────────────────────────────────

  describe('calcAnomalyRate', () => {
    it('calculates anomaly rate as percentage', () => {
      expect(calcAnomalyRate(3, 20)).toBeCloseTo(15)
    })

    it('returns 0 when totalChecked is 0', () => {
      expect(calcAnomalyRate(5, 0)).toBe(0)
    })
  })

  // ─── calcCoverageRate ─────────────────────────────────────────────────────

  describe('calcCoverageRate', () => {
    it('calculates coverage rate as percentage', () => {
      expect(calcCoverageRate(500000, 1000000)).toBeCloseTo(50)
    })

    it('returns 0 when revenueTotal is 0', () => {
      expect(calcCoverageRate(100, 0)).toBe(0)
    })
  })

  // ─── isCrossPeriod ────────────────────────────────────────────────────────

  describe('isCrossPeriod', () => {
    const bsDate = '2024-12-31'

    it('returns true when voucher before BS and reference after BS', () => {
      expect(isCrossPeriod('2024-12-28', '2025-01-05', bsDate)).toBe(true)
    })

    it('returns true when voucher after BS and reference before BS', () => {
      expect(isCrossPeriod('2025-01-03', '2024-12-25', bsDate)).toBe(true)
    })

    it('returns false when both before BS date', () => {
      expect(isCrossPeriod('2024-12-20', '2024-12-25', bsDate)).toBe(false)
    })

    it('returns false when both after BS date', () => {
      expect(isCrossPeriod('2025-01-02', '2025-01-10', bsDate)).toBe(false)
    })

    it('returns true when one equals BS date (on boundary)', () => {
      expect(isCrossPeriod('2024-12-31', '2025-01-05', bsDate)).toBe(true)
    })

    it('returns false for invalid dates', () => {
      expect(isCrossPeriod('invalid', '2024-12-25', bsDate)).toBe(false)
    })
  })

  // ─── calcCrossPeriodDays ──────────────────────────────────────────────────

  describe('calcCrossPeriodDays', () => {
    it('calculates absolute day difference', () => {
      expect(calcCrossPeriodDays('2024-12-28', '2025-01-03')).toBe(6)
    })

    it('is symmetric (order does not matter)', () => {
      expect(calcCrossPeriodDays('2025-01-03', '2024-12-28')).toBe(6)
    })

    it('returns 0 for same date', () => {
      expect(calcCrossPeriodDays('2024-12-31', '2024-12-31')).toBe(0)
    })

    it('returns 0 for invalid dates', () => {
      expect(calcCrossPeriodDays('invalid', '2024-12-31')).toBe(0)
    })
  })

  // ─── isSuspiciousFundFlow ─────────────────────────────────────────────────

  describe('isSuspiciousFundFlow', () => {
    it('returns true when amounts close and days < 30', () => {
      expect(isSuspiciousFundFlow(100000, 98000, 5)).toBe(true)
    })

    it('returns false when amounts differ significantly', () => {
      expect(isSuspiciousFundFlow(100000, 50000, 5)).toBe(false)
    })

    it('returns false when days >= 30', () => {
      expect(isSuspiciousFundFlow(100000, 99000, 30)).toBe(false)
    })

    it('uses custom threshold', () => {
      // 5% threshold: diff=5000/100000=5% → not < 5%, so false
      expect(isSuspiciousFundFlow(100000, 95000, 5, 0.05)).toBe(false)
      // 4% diff < 5% threshold → true
      expect(isSuspiciousFundFlow(100000, 96000, 5, 0.05)).toBe(true)
    })

    it('returns false when both amounts are 0', () => {
      expect(isSuspiciousFundFlow(0, 0, 5)).toBe(false)
    })
  })

  // ─── isIpoGroupVisible ───────────────────────────────────────────────────

  describe('isIpoGroupVisible', () => {
    it('returns true for ipo keyword', () => {
      expect(isIpoGroupVisible('ipo')).toBe(true)
      expect(isIpoGroupVisible('IPO审计')).toBe(true)
    })

    it('returns true for listed keyword', () => {
      expect(isIpoGroupVisible('listed_company')).toBe(true)
    })

    it('returns true for neeq keyword', () => {
      expect(isIpoGroupVisible('NEEQ')).toBe(true)
    })

    it('returns true for restructuring keyword', () => {
      expect(isIpoGroupVisible('major_restructuring')).toBe(true)
    })

    it('returns true for fraud_risk keyword', () => {
      expect(isIpoGroupVisible('fraud_risk_high')).toBe(true)
    })

    it('returns false for normal business', () => {
      expect(isIpoGroupVisible('normal')).toBe(false)
      expect(isIpoGroupVisible('general_audit')).toBe(false)
    })

    it('is case insensitive', () => {
      expect(isIpoGroupVisible('IPO')).toBe(true)
      expect(isIpoGroupVisible('Listed')).toBe(true)
      expect(isIpoGroupVisible('FRAUD_RISK')).toBe(true)
    })

    it('handles empty string', () => {
      expect(isIpoGroupVisible('')).toBe(false)
    })
  })

  // ─── isCrossPeriodForward / isCrossPeriodBackward（D4-36 方向化跨期）──────────

  describe('isCrossPeriodForward', () => {
    it('凭证期内且单据期后 → 跨期 true', () => {
      // 凭证 2024-12-30 ≤ 截止 2024-12-31，单据 2025-01-03 > 截止
      expect(isCrossPeriodForward('2024-12-30', '2025-01-03', '2024-12-31')).toBe(true)
    })
    it('凭证与单据均在期内 → 非跨期 false', () => {
      expect(isCrossPeriodForward('2024-12-20', '2024-12-28', '2024-12-31')).toBe(false)
    })
    it('无效日期 → false', () => {
      expect(isCrossPeriodForward('', '2025-01-03', '2024-12-31')).toBe(false)
    })
  })

  describe('isCrossPeriodBackward', () => {
    it('单据期内且凭证期后 → 跨期 true', () => {
      // 单据 2024-12-29 ≤ 截止，凭证 2025-01-05 > 截止
      expect(isCrossPeriodBackward('2024-12-29', '2025-01-05', '2024-12-31')).toBe(true)
    })
    it('单据与凭证均在期内 → 非跨期 false', () => {
      expect(isCrossPeriodBackward('2024-12-20', '2024-12-28', '2024-12-31')).toBe(false)
    })
  })

  describe('forward/backward 方向相反', () => {
    it('同一组日期在两个方向下结果相反（一真一假）', () => {
      // 凭证 2024-12-30（期内）、单据 2025-01-03（期后）
      // forward（账到单据：凭证期内+单据期后）→ 跨期 true
      // backward（单据到账：单据期内+凭证期后）→ 单据不在期内 → false
      const v = '2024-12-30', d = '2025-01-03', c = '2024-12-31'
      expect(isCrossPeriodForward(v, d, c)).toBe(true)
      expect(isCrossPeriodBackward(d, v, c)).toBe(false)
    })
  })

  // ─── 表间 WP 取数 / 预设二次编辑 ─────────────────────────────────────────
  describe('parseWpFormulaRef + D4-10 preset', () => {
    it('解析合法两参 WP', () => {
      expect(parseWpFormulaRef(D4_10_TOTAL_AMOUNT_PRESET)).toEqual({
        wpCode: 'D4-2',
        field: '本期未审合计',
      })
    })
    it('非法表达式 fail closed → null', () => {
      expect(parseWpFormulaRef("WP(D4-2,合计)")).toBeNull()
      expect(parseWpFormulaRef('')).toBeNull()
      expect(parseWpFormulaRef(null)).toBeNull()
    })
  })

  describe('resolveD42PeriodUnadjustedTotal', () => {
    it('Σ months 为未审合计，不含 auditAdjustment', () => {
      const total = resolveD42PeriodUnadjustedTotal([
        { months: [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
        { months: [50, 50, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
      ])
      expect(total).toBe(200)
    })
    it('优先用已算好的 periodTotal', () => {
      expect(resolveD42PeriodUnadjustedTotal([{ periodTotal: 1234, months: [1] }])).toBe(1234)
    })
  })

  describe('resolvePresetOrOverride', () => {
    it('未覆盖时用 preset；覆盖时保留 stored', () => {
      expect(resolvePresetOrOverride({ presetValue: 100, storedValue: 9, manualOverride: false })).toBe(100)
      expect(resolvePresetOrOverride({ presetValue: 100, storedValue: 9, manualOverride: true })).toBe(9)
    })
    it('上游为 0 且未覆盖 → 保留 stored（不造 0）', () => {
      expect(resolvePresetOrOverride({ presetValue: 0, storedValue: 88, manualOverride: false })).toBe(88)
    })
  })
})
