/**
 * K8 销售费用 — 三引擎单元测试（确定性）
 *
 * 覆盖三个纯函数composable:
 * 1. useK8FormulaEngine — 审定数/发生额/合计
 * 2. useK8AnalysisEngine — 同比变动率/占收入比/异常判断
 * 3. useK8CutoffEngine — 跨期判断/自动抽样
 *
 * PBT测试另文覆盖随机输入。本文件覆盖具体边界值和业务场景。
 *
 * Spec: .kiro/specs/k8-selling-expenses/ Task 7.1
 * Validates: CP-K8-01~07
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSubtotal,
} from '../composables/useK8FormulaEngine'
import {
  calcYoYChange,
  calcRatioToRevenue,
  isAbnormalFluctuation,
} from '../composables/useK8AnalysisEngine'
import {
  isCrossPeriod,
  autoSampleCutoff,
} from '../composables/useK8CutoffEngine'
import type { LedgerEntry } from '../composables/useK8CutoffEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. useK8FormulaEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── calcAuditedAmount 审定数=未审+AJE+RJE (CP-K8-01) ─────────────────────

describe('useK8FormulaEngine — calcAuditedAmount', () => {
  it('正常计算: 100+20+(-5)=115', () => {
    expect(calcAuditedAmount(100, 20, -5)).toBe(115)
  })

  it('全零输入返回0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数场景: (-100)+50+30=-20', () => {
    expect(calcAuditedAmount(-100, 50, 30)).toBe(-20)
  })

  it('大数场景: 千万级金额', () => {
    expect(calcAuditedAmount(10000000, 500000, -200000)).toBe(10300000)
  })

  it('NaN/null安全防御', () => {
    expect(calcAuditedAmount(NaN as any, 100, 50)).toBe(150)
  })
})

// ─── calcIncomeStatementOccurrence 费用发生额=借方-贷方 (CP-K8-02) ────────

describe('useK8FormulaEngine — calcIncomeStatementOccurrence', () => {
  it('正常: 借方50000-贷方10000=40000', () => {
    expect(calcIncomeStatementOccurrence(50000, 10000)).toBe(40000)
  })

  it('红冲(dr<cr): 10000-50000=-40000', () => {
    expect(calcIncomeStatementOccurrence(10000, 50000)).toBe(-40000)
  })

  it('借贷相等返回0', () => {
    expect(calcIncomeStatementOccurrence(30000, 30000)).toBe(0)
  })

  it('零值场景', () => {
    expect(calcIncomeStatementOccurrence(0, 0)).toBe(0)
  })

  it('贷方为0时等于借方', () => {
    expect(calcIncomeStatementOccurrence(80000, 0)).toBe(80000)
  })
})

// ─── calcSubtotal 合计行恒等 (CP-K8-06) ─────────────────────────────────────

describe('useK8FormulaEngine — calcSubtotal', () => {
  it('空数组=0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('正负混合: [100,-20,50]=130', () => {
    expect(calcSubtotal([100, -20, 50])).toBe(130)
  })

  it('大数组(10个元素)', () => {
    const arr = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    expect(calcSubtotal(arr)).toBe(55)
  })

  it('非数组输入返回0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. useK8AnalysisEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── calcYoYChange 同比变动率=(本期-上期)/|上期| (CP-K8-03) ────────────────

describe('useK8AnalysisEngine — calcYoYChange', () => {
  it('正常除法: (120-100)/100=0.2', () => {
    expect(calcYoYChange(120, 100)).toBeCloseTo(0.2)
  })

  it('prior=0返回null', () => {
    expect(calcYoYChange(50, 0)).toBeNull()
  })

  it('下降场景: (80-100)/100=-0.2', () => {
    expect(calcYoYChange(80, 100)).toBeCloseTo(-0.2)
  })

  it('无变化: (100-100)/100=0', () => {
    expect(calcYoYChange(100, 100)).toBe(0)
  })

  it('同号负值上期: (50-(-100))/|-100|=1.5', () => {
    expect(calcYoYChange(50, -100)).toBeCloseTo(1.5)
  })

  it('本期为0: (0-200)/|200|=-1', () => {
    expect(calcYoYChange(0, 200)).toBeCloseTo(-1)
  })
})

// ─── calcRatioToRevenue 占收入比=费用/营业收入 (CP-K8-04) ────────────────────

describe('useK8AnalysisEngine — calcRatioToRevenue', () => {
  it('正常: 10000/100000=0.1', () => {
    expect(calcRatioToRevenue(10000, 100000)).toBeCloseTo(0.1)
  })

  it('revenue=0返回null', () => {
    expect(calcRatioToRevenue(5000, 0)).toBeNull()
  })

  it('负费用: -5000/100000=-0.05', () => {
    expect(calcRatioToRevenue(-5000, 100000)).toBeCloseTo(-0.05)
  })

  it('费用为0: 0/100000=0', () => {
    expect(calcRatioToRevenue(0, 100000)).toBe(0)
  })

  it('费用大于收入: 150000/100000=1.5', () => {
    expect(calcRatioToRevenue(150000, 100000)).toBeCloseTo(1.5)
  })
})

// ─── isAbnormalFluctuation |变动率|>阈值 (CP-K8-05) ──────────────────────────

describe('useK8AnalysisEngine — isAbnormalFluctuation', () => {
  it('|0.5|>0.3 = true (正向超阈值)', () => {
    expect(isAbnormalFluctuation(0.5, 0.3)).toBe(true)
  })

  it('|-0.5|>0.3 = true (负向超阈值)', () => {
    expect(isAbnormalFluctuation(-0.5, 0.3)).toBe(true)
  })

  it('|0.3|>0.3 = false (等于阈值不算异常)', () => {
    expect(isAbnormalFluctuation(0.3, 0.3)).toBe(false)
  })

  it('|0.1|>0.3 = false (小于阈值)', () => {
    expect(isAbnormalFluctuation(0.1, 0.3)).toBe(false)
  })

  it('|0|>0.3 = false (零变动)', () => {
    expect(isAbnormalFluctuation(0, 0.3)).toBe(false)
  })

  it('阈值为0时任何非零变动都异常', () => {
    expect(isAbnormalFluctuation(0.01, 0)).toBe(true)
    expect(isAbnormalFluctuation(0, 0)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. useK8CutoffEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── isCrossPeriod 跨期判断 (CP-K8-07) ──────────────────────────────────────

describe('useK8CutoffEngine — isCrossPeriod', () => {
  it('同期(同年同月)返回false', () => {
    expect(isCrossPeriod('2025-12-28', '2025-12-31', '2025-12-31')).toBe(false)
  })

  it('跨期(不同月)返回true', () => {
    expect(isCrossPeriod('2025-11-30', '2025-12-05', '2025-12-31')).toBe(true)
  })

  it('跨年返回true', () => {
    expect(isCrossPeriod('2024-12-30', '2025-01-02', '2025-12-31')).toBe(true)
  })

  it('边界：期末当天同月不跨期', () => {
    expect(isCrossPeriod('2025-12-31', '2025-12-31', '2025-12-31')).toBe(false)
  })

  it('边界：1月1日 vs 12月31日跨期', () => {
    expect(isCrossPeriod('2026-01-01', '2025-12-31', '2025-12-31')).toBe(true)
  })

  it('无效日期返回false', () => {
    expect(isCrossPeriod('', '2025-12-31', '2025-12-31')).toBe(false)
    expect(isCrossPeriod('invalid', '2025-12-31', '2025-12-31')).toBe(false)
  })
})

// ─── autoSampleCutoff 过滤±days天 ───────────────────────────────────────────

describe('useK8CutoffEngine — autoSampleCutoff', () => {
  const makeLedger = (dates: string[]): LedgerEntry[] =>
    dates.map((d, i) => ({
      voucherNo: `V-${i + 1}`,
      voucherDate: d,
      summary: `摘要${i + 1}`,
      debitAmount: 1000 * (i + 1),
      creditAmount: null,
      accountCode: '6601',
      accountName: '销售费用',
      sourceDate: null,
    }))

  it('过滤±5天窗口', () => {
    // periodEnd=2025-12-31, ±5天=[12-26, 01-05]
    const entries = makeLedger([
      '2025-12-20', // 外
      '2025-12-26', // 边界(期末-5天)
      '2025-12-28', // 内
      '2025-12-31', // 期末当天
      '2026-01-03', // 内
      '2026-01-05', // 边界(期末+5天)
      '2026-01-10', // 外
    ])
    const result = autoSampleCutoff(entries, '2025-12-31', 5)
    expect(result.length).toBe(5) // 12-26,12-28,12-31,01-03,01-05
    expect(result.map(s => s.bookDate)).toEqual([
      '2025-12-26',
      '2025-12-28',
      '2025-12-31',
      '2026-01-03',
      '2026-01-05',
    ])
  })

  it('空数组返回空', () => {
    expect(autoSampleCutoff([], '2025-12-31', 5)).toEqual([])
  })

  it('无有效periodEnd返回空', () => {
    const entries = makeLedger(['2025-12-30'])
    expect(autoSampleCutoff(entries, '', 5)).toEqual([])
    expect(autoSampleCutoff(entries, 'invalid', 5)).toEqual([])
  })

  it('有sourceDate时自动计算isCrossPeriod', () => {
    const entries: LedgerEntry[] = [
      {
        voucherNo: 'V-1',
        voucherDate: '2025-12-30',
        summary: '跨期费用',
        debitAmount: 5000,
        creditAmount: null,
        accountCode: '6601',
        accountName: '销售费用',
        sourceDate: '2025-11-25', // 不同月，跨期
      },
      {
        voucherNo: 'V-2',
        voucherDate: '2025-12-30',
        summary: '正常费用',
        debitAmount: 3000,
        creditAmount: null,
        accountCode: '6601',
        accountName: '销售费用',
        sourceDate: '2025-12-28', // 同月，不跨期
      },
    ]
    const result = autoSampleCutoff(entries, '2025-12-31', 5)
    expect(result.length).toBe(2)
    expect(result[0].isCrossPeriod).toBe(true)
    expect(result[1].isCrossPeriod).toBe(false)
  })

  it('sourceDate为null时isCrossPeriod=false', () => {
    const entries: LedgerEntry[] = [
      {
        voucherNo: 'V-1',
        voucherDate: '2025-12-30',
        summary: '无原始凭证日期',
        debitAmount: 2000,
        creditAmount: null,
        accountCode: '6601',
        accountName: '销售费用',
        sourceDate: null,
      },
    ]
    const result = autoSampleCutoff(entries, '2025-12-31', 5)
    expect(result.length).toBe(1)
    expect(result[0].isCrossPeriod).toBe(false)
  })

  it('边界日期(恰好±5天)包含在样本中', () => {
    const entries = makeLedger(['2025-12-26', '2026-01-05'])
    const result = autoSampleCutoff(entries, '2025-12-31', 5)
    expect(result.length).toBe(2)
  })
})
