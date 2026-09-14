/**
 * K9 管理费用 — 单元测试（边界与异常场景）
 *
 * Spec: .kiro/specs/k9-admin-expenses/ Task 7.1
 * Requirements: CP-K9-01~07
 *
 * 覆盖 useK9FormulaEngine + useK9AnalysisEngine + useK9CutoffEngine
 * 边界/异常 edge cases NOT covered by PBT:
 * - parseNum: garbage inputs (null, undefined, NaN, Infinity, empty, "abc")
 * - calcAuditedAmount: zero args
 * - calcIncomeStatementOccurrence: negative debit/credit (红冲场景)
 * - calcSubtotal: non-array, array with NaN values
 * - calcYoYChange: prior=0 → null, prior negative
 * - calcRatioToRevenue: revenue=0 → null
 * - isAbnormalFluctuation: exactly at threshold (边界)
 * - isCrossPeriod: invalid dates, same day different month, leap year
 * - autoSampleCutoff: empty ledger, invalid periodEnd, negative days
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSubtotal,
} from '../composables/useK9FormulaEngine'
import {
  calcYoYChange,
  calcRatioToRevenue,
  isAbnormalFluctuation,
} from '../composables/useK9AnalysisEngine'
import {
  isCrossPeriod,
  autoSampleCutoff,
  type LedgerEntry,
} from '../composables/useK9CutoffEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// parseNum 边界
// ═══════════════════════════════════════════════════════════════════════════════

describe('parseNum — garbage inputs', () => {
  it('null → 0', () => {
    expect(parseNum(null)).toBe(0)
  })

  it('undefined → 0', () => {
    expect(parseNum(undefined)).toBe(0)
  })

  it('NaN → 0', () => {
    expect(parseNum(NaN)).toBe(0)
  })

  it('Infinity → 0', () => {
    expect(parseNum(Infinity)).toBe(0)
  })

  it('-Infinity → 0', () => {
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('empty string → 0', () => {
    expect(parseNum('')).toBe(0)
  })

  it('"abc" → 0', () => {
    expect(parseNum('abc')).toBe(0)
  })

  it('"NaN" string → 0', () => {
    expect(parseNum('NaN')).toBe(0)
  })

  it('"123.45" string → 123.45', () => {
    expect(parseNum('123.45')).toBeCloseTo(123.45)
  })

  it('" 42 " whitespace padding → 42', () => {
    expect(parseNum(' 42 ')).toBe(42)
  })

  it('0 → 0 (number)', () => {
    expect(parseNum(0)).toBe(0)
  })

  it('-100 → -100', () => {
    expect(parseNum(-100)).toBe(-100)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcAuditedAmount 边界
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAuditedAmount — edge cases', () => {
  it('全部为0时返回0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('只有未审数（AJE=0, RJE=0）', () => {
    expect(calcAuditedAmount(1000, 0, 0)).toBe(1000)
  })

  it('负数AJE（冲回调整）', () => {
    expect(calcAuditedAmount(1000, -200, 0)).toBe(800)
  })

  it('负数RJE（重分类减少）', () => {
    expect(calcAuditedAmount(500, 0, -100)).toBe(400)
  })

  it('三者均为负数', () => {
    expect(calcAuditedAmount(-100, -50, -30)).toBe(-180)
  })

  it('大数值精度', () => {
    const result = calcAuditedAmount(1e12, 5e11, 3e11)
    expect(result).toBe(1.8e12)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcIncomeStatementOccurrence — 负数debit/credit (红冲)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcIncomeStatementOccurrence — negative debit/credit (红冲)', () => {
  it('正常场景：借方-贷方', () => {
    expect(calcIncomeStatementOccurrence(5000, 1000)).toBe(4000)
  })

  it('负数借方（实务中不常见但应正常计算）', () => {
    expect(calcIncomeStatementOccurrence(-500, 1000)).toBe(-1500)
  })

  it('负数贷方（红冲冲回）', () => {
    expect(calcIncomeStatementOccurrence(3000, -200)).toBe(3200)
  })

  it('两者均为负数', () => {
    expect(calcIncomeStatementOccurrence(-100, -200)).toBe(100)
  })

  it('两者均为0', () => {
    expect(calcIncomeStatementOccurrence(0, 0)).toBe(0)
  })

  it('贷方大于借方（期末结转后净额为负）', () => {
    expect(calcIncomeStatementOccurrence(1000, 3000)).toBe(-2000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcSubtotal — non-array / NaN values
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcSubtotal — edge cases', () => {
  it('非数组输入返回0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
    expect(calcSubtotal('hello' as any)).toBe(0)
    expect(calcSubtotal(123 as any)).toBe(0)
  })

  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('数组含NaN值 → NaN视为0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('数组含Infinity → Infinity视为0', () => {
    expect(calcSubtotal([100, Infinity, 200])).toBe(300)
  })

  it('数组含null/undefined → 视为0', () => {
    expect(calcSubtotal([100, null as any, undefined as any, 200])).toBe(300)
  })

  it('单元素数组', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('全部为负数', () => {
    expect(calcSubtotal([-10, -20, -30])).toBe(-60)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcYoYChange — prior=0 / prior负数
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcYoYChange — division edge cases', () => {
  it('prior=0 → null (除零)', () => {
    expect(calcYoYChange(100, 0)).toBeNull()
  })

  it('prior=0, current=0 → null', () => {
    expect(calcYoYChange(0, 0)).toBeNull()
  })

  it('prior负数（上期为负费用）→ 正常计算', () => {
    // (100 - (-50)) / |−50| = 150/50 = 3.0
    const result = calcYoYChange(100, -50)
    expect(result).not.toBeNull()
    expect(result).toBeCloseTo(3.0)
  })

  it('prior负数，current也负 → 正确计算', () => {
    // (-30 - (-50)) / |−50| = 20/50 = 0.4
    const result = calcYoYChange(-30, -50)
    expect(result).toBeCloseTo(0.4)
  })

  it('current = prior → 变动率为0', () => {
    expect(calcYoYChange(200, 200)).toBeCloseTo(0)
  })

  it('current=0, prior有值 → 负变动率', () => {
    // (0 - 100) / |100| = -1.0
    expect(calcYoYChange(0, 100)).toBeCloseTo(-1.0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcRatioToRevenue — revenue=0
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcRatioToRevenue — edge cases', () => {
  it('revenue=0 → null (除零)', () => {
    expect(calcRatioToRevenue(500, 0)).toBeNull()
  })

  it('expense=0, revenue>0 → 0', () => {
    expect(calcRatioToRevenue(0, 10000)).toBe(0)
  })

  it('费用大于收入 → 占比>1', () => {
    const result = calcRatioToRevenue(15000, 10000)
    expect(result).toBeCloseTo(1.5)
  })

  it('负费用（冲回）→ 负比率', () => {
    const result = calcRatioToRevenue(-500, 10000)
    expect(result).toBeCloseTo(-0.05)
  })

  it('负营业收入 → 正常计算（特殊行业场景）', () => {
    const result = calcRatioToRevenue(500, -10000)
    expect(result).toBeCloseTo(-0.05)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// isAbnormalFluctuation — exactly at threshold (边界)
// ═══════════════════════════════════════════════════════════════════════════════

describe('isAbnormalFluctuation — threshold boundary', () => {
  it('|rate| = threshold → false (严格大于才异常)', () => {
    expect(isAbnormalFluctuation(0.3, 0.3)).toBe(false)
  })

  it('|rate| 略大于 threshold → true', () => {
    expect(isAbnormalFluctuation(0.301, 0.3)).toBe(true)
  })

  it('|rate| 略小于 threshold → false', () => {
    expect(isAbnormalFluctuation(0.299, 0.3)).toBe(false)
  })

  it('负变动率 at -threshold → false', () => {
    expect(isAbnormalFluctuation(-0.3, 0.3)).toBe(false)
  })

  it('负变动率 超过 threshold → true', () => {
    expect(isAbnormalFluctuation(-0.5, 0.3)).toBe(true)
  })

  it('rate=0, threshold=0 → false (|0|>0 is false)', () => {
    expect(isAbnormalFluctuation(0, 0)).toBe(false)
  })

  it('threshold=0, rate>0 → true', () => {
    expect(isAbnormalFluctuation(0.001, 0)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// isCrossPeriod — invalid dates / leap year / boundaries
// ═══════════════════════════════════════════════════════════════════════════════

describe('isCrossPeriod — edge cases', () => {
  it('无效sourceDate → false (无法判断)', () => {
    expect(isCrossPeriod('', '2025-01-15', '2025-12-31')).toBe(false)
    expect(isCrossPeriod('invalid', '2025-01-15', '2025-12-31')).toBe(false)
    expect(isCrossPeriod('2025-13-01', '2025-01-15', '2025-12-31')).toBe(false)
  })

  it('无效bookDate → false', () => {
    expect(isCrossPeriod('2025-01-15', '', '2025-12-31')).toBe(false)
    expect(isCrossPeriod('2025-01-15', 'abc', '2025-12-31')).toBe(false)
    expect(isCrossPeriod('2025-01-15', '2025-00-01', '2025-12-31')).toBe(false)
  })

  it('同一天（同年同月同日）→ false', () => {
    expect(isCrossPeriod('2025-12-31', '2025-12-31', '2025-12-31')).toBe(false)
  })

  it('同月不同日 → false', () => {
    expect(isCrossPeriod('2025-12-28', '2025-12-31', '2025-12-31')).toBe(false)
  })

  it('不同月份（12月原始→1月记账）→ true', () => {
    expect(isCrossPeriod('2025-12-30', '2026-01-02', '2025-12-31')).toBe(true)
  })

  it('不同月份（1月原始→12月记账）→ true', () => {
    expect(isCrossPeriod('2026-01-05', '2025-12-28', '2025-12-31')).toBe(true)
  })

  it('闰年2月29日 → 有效日期，正确判断', () => {
    // 2024是闰年
    expect(isCrossPeriod('2024-02-29', '2024-02-15', '2024-12-31')).toBe(false)
    expect(isCrossPeriod('2024-02-29', '2024-03-01', '2024-12-31')).toBe(true)
  })

  it('非闰年2月29日 → 无效日期 → false', () => {
    // 2025不是闰年，2月29日无效
    expect(isCrossPeriod('2025-02-29', '2025-03-01', '2025-12-31')).toBe(false)
  })

  it('月末边界：1月31日原始 + 2月1日记账 → true', () => {
    expect(isCrossPeriod('2025-01-31', '2025-02-01', '2025-12-31')).toBe(true)
  })

  it('两个日期都是null → false', () => {
    expect(isCrossPeriod(null as any, null as any, '2025-12-31')).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// autoSampleCutoff — empty/invalid inputs
// ═══════════════════════════════════════════════════════════════════════════════

describe('autoSampleCutoff — edge cases', () => {
  it('空ledger数组 → 返回空数组', () => {
    expect(autoSampleCutoff([], '2025-12-31', 5)).toEqual([])
  })

  it('非数组 ledger → 返回空数组', () => {
    expect(autoSampleCutoff(null as any, '2025-12-31', 5)).toEqual([])
    expect(autoSampleCutoff(undefined as any, '2025-12-31', 5)).toEqual([])
  })

  it('无效periodEnd → 返回空数组', () => {
    const ledger: LedgerEntry[] = [
      { voucherDate: '2025-12-30', voucherNo: 'V001' },
    ]
    expect(autoSampleCutoff(ledger, '', 5)).toEqual([])
    expect(autoSampleCutoff(ledger, 'invalid', 5)).toEqual([])
  })

  it('负数days → 视为0，只包含期末当天', () => {
    const ledger: LedgerEntry[] = [
      { voucherDate: '2025-12-31', voucherNo: 'V001' },
      { voucherDate: '2025-12-30', voucherNo: 'V002' },
    ]
    const result = autoSampleCutoff(ledger, '2025-12-31', -5)
    // days=0：只有恰好在期末当天的才在窗口内
    expect(result.length).toBe(1)
    expect(result[0].entry.voucherNo).toBe('V001')
  })

  it('正常场景：期末±5天窗口内筛选', () => {
    const ledger: LedgerEntry[] = [
      { voucherDate: '2025-12-25', voucherNo: 'V-early' },   // 12.31-5=12.26之前，不在窗口
      { voucherDate: '2025-12-26', voucherNo: 'V-boundary' }, // 刚好在窗口内
      { voucherDate: '2025-12-30', voucherNo: 'V-before' },
      { voucherDate: '2025-12-31', voucherNo: 'V-end' },      // 期末当天
      { voucherDate: '2026-01-03', voucherNo: 'V-after' },
      { voucherDate: '2026-01-05', voucherNo: 'V-boundary2' }, // 12.31+5=1.5，刚好在窗口内
      { voucherDate: '2026-01-06', voucherNo: 'V-late' },      // 窗口外
    ]
    const result = autoSampleCutoff(ledger, '2025-12-31', 5)
    // 窗口 [12-26, 01-05]，包含边界
    expect(result.length).toBe(5)
    const voucherNos = result.map(s => s.entry.voucherNo)
    expect(voucherNos).toContain('V-boundary')
    expect(voucherNos).toContain('V-before')
    expect(voucherNos).toContain('V-end')
    expect(voucherNos).toContain('V-after')
    expect(voucherNos).toContain('V-boundary2')
    expect(voucherNos).not.toContain('V-early')
    expect(voucherNos).not.toContain('V-late')
  })

  it('direction属性正确标记（before/after period end）', () => {
    const ledger: LedgerEntry[] = [
      { voucherDate: '2025-12-29', voucherNo: 'V-before' },
      { voucherDate: '2025-12-31', voucherNo: 'V-end' },
      { voucherDate: '2026-01-02', voucherNo: 'V-after' },
    ]
    const result = autoSampleCutoff(ledger, '2025-12-31', 5)
    const beforeSample = result.find(s => s.entry.voucherNo === 'V-before')
    const endSample = result.find(s => s.entry.voucherNo === 'V-end')
    const afterSample = result.find(s => s.entry.voucherNo === 'V-after')

    expect(beforeSample?.direction).toBe('before_period_end')
    expect(beforeSample?.daysDiff).toBeLessThan(0)
    expect(endSample?.direction).toBe('before_period_end') // daysDiff=0 → before
    expect(endSample?.daysDiff).toBe(0)
    expect(afterSample?.direction).toBe('after_period_end')
    expect(afterSample?.daysDiff).toBeGreaterThan(0)
  })

  it('ledger含无效voucherDate条目 → 跳过', () => {
    const ledger: LedgerEntry[] = [
      { voucherDate: '', voucherNo: 'V-invalid' },
      { voucherDate: 'not-a-date', voucherNo: 'V-bad' },
      { voucherDate: '2025-12-30', voucherNo: 'V-good' },
    ]
    const result = autoSampleCutoff(ledger, '2025-12-31', 5)
    expect(result.length).toBe(1)
    expect(result[0].entry.voucherNo).toBe('V-good')
  })
})
