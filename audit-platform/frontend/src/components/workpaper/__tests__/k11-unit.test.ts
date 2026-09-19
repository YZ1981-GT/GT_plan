/**
 * K11 资产减值损失 — 公式引擎 + 减值汇总引擎 单元测试
 *
 * 覆盖 useK11FormulaEngine + useK11ImpairmentSummaryEngine 全部纯函数的
 * 确定性边界测试（非PBT），与 k11-pbt.test.ts 互补。
 *
 * 科目：6701资产减值损失（损益类/借方科目，取发生额非余额）
 * Requirements: CP-K11-01~05
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSourceVariance,
  calcSubtotal,
} from '../composables/useK11FormulaEngine'
import { calcImpairmentSummary } from '../composables/useK11ImpairmentSummaryEngine'

// ═══════════════════════════════════════════════════════════════
// parseNum — 安全数字解析
// ═══════════════════════════════════════════════════════════════
describe('parseNum — 安全数字解析', () => {
  it('有效数字直接返回', () => {
    expect(parseNum(100)).toBe(100)
    expect(parseNum(-50.5)).toBe(-50.5)
    expect(parseNum(0)).toBe(0)
  })

  it('字符串数字正确解析', () => {
    expect(parseNum('123.45')).toBe(123.45)
    expect(parseNum('-99')).toBe(-99)
    expect(parseNum(' 42 ')).toBe(42)
    expect(parseNum('0')).toBe(0)
  })

  it('NaN → 0', () => {
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum('NaN')).toBe(0)
  })

  it('null → 0', () => {
    expect(parseNum(null)).toBe(0)
  })

  it('undefined → 0', () => {
    expect(parseNum(undefined)).toBe(0)
  })

  it('Infinity → 0', () => {
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('空字符串 → 0', () => {
    expect(parseNum('')).toBe(0)
    expect(parseNum('   ')).toBe(0)
  })

  it('非数字字符串 → 0', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum('12abc')).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════
// CP-K11-01: calcAuditedAmount — 审定数=未审+AJE+RJE
// ═══════════════════════════════════════════════════════════════
describe('calcAuditedAmount — 审定数=未审+AJE+RJE (CP-K11-01)', () => {
  it('基础正数计算', () => {
    expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
  })

  it('含负数调整', () => {
    expect(calcAuditedAmount(5000, -300, -100)).toBe(4600)
  })

  it('全零返回0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('AJE和RJE为0时等于未审数', () => {
    expect(calcAuditedAmount(888, 0, 0)).toBe(888)
  })

  it('未审为0时等于调整合计', () => {
    expect(calcAuditedAmount(0, 100, 200)).toBe(300)
  })

  it('负未审数情况（红冲）', () => {
    expect(calcAuditedAmount(-500, 100, 0)).toBe(-400)
  })

  it('NaN输入防御（视为0）', () => {
    expect(calcAuditedAmount(NaN, 100, 50)).toBe(150)
    expect(calcAuditedAmount(1000, NaN, NaN)).toBe(1000)
  })

  it('大数值计算', () => {
    expect(calcAuditedAmount(1e8, 5e6, 2e6)).toBe(107000000)
  })
})

// ═══════════════════════════════════════════════════════════════
// CP-K11-02: calcIncomeStatementOccurrence — 损益发生额=借-贷
// ═══════════════════════════════════════════════════════════════
describe('calcIncomeStatementOccurrence — 损益发生额=借-贷 (CP-K11-02)', () => {
  it('借方>贷方（净计提）', () => {
    expect(calcIncomeStatementOccurrence(5000, 1000)).toBe(4000)
  })

  it('借方<贷方（净转回）', () => {
    expect(calcIncomeStatementOccurrence(1000, 3000)).toBe(-2000)
  })

  it('借方=贷方（净额为0）', () => {
    expect(calcIncomeStatementOccurrence(2000, 2000)).toBe(0)
  })

  it('贷方为0（纯计提无转回）', () => {
    expect(calcIncomeStatementOccurrence(8000, 0)).toBe(8000)
  })

  it('借方为0（纯转回）', () => {
    expect(calcIncomeStatementOccurrence(0, 500)).toBe(-500)
  })

  it('两者皆为0', () => {
    expect(calcIncomeStatementOccurrence(0, 0)).toBe(0)
  })

  it('负数输入检测（异常场景防御）', () => {
    // 负数不应出现但parseNum会处理
    expect(calcIncomeStatementOccurrence(-100, 200)).toBe(-300)
    expect(calcIncomeStatementOccurrence(100, -200)).toBe(300)
  })

  it('NaN输入防御', () => {
    expect(calcIncomeStatementOccurrence(NaN, 500)).toBe(-500)
    expect(calcIncomeStatementOccurrence(500, NaN)).toBe(500)
  })
})

// ═══════════════════════════════════════════════════════════════
// CP-K11-04: calcSourceVariance — 源底稿核对差异
// ═══════════════════════════════════════════════════════════════
describe('calcSourceVariance — 源底稿核对差异 (CP-K11-04)', () => {
  it('K11与源底稿一致（差异=0）', () => {
    expect(calcSourceVariance(5000, 5000)).toBe(0)
  })

  it('K11大于源底稿（正差异）', () => {
    expect(calcSourceVariance(6000, 5000)).toBe(1000)
  })

  it('K11小于源底稿（负差异）', () => {
    expect(calcSourceVariance(3000, 5000)).toBe(-2000)
  })

  it('零值情况', () => {
    expect(calcSourceVariance(0, 0)).toBe(0)
    expect(calcSourceVariance(100, 0)).toBe(100)
    expect(calcSourceVariance(0, 100)).toBe(-100)
  })

  it('NaN输入防御', () => {
    expect(calcSourceVariance(NaN, 1000)).toBe(-1000)
    expect(calcSourceVariance(1000, NaN)).toBe(1000)
  })

  it('负数金额（异常场景）', () => {
    expect(calcSourceVariance(-500, -300)).toBe(-200)
  })
})

// ═══════════════════════════════════════════════════════════════
// CP-K11-05: calcSubtotal — 合计行求和
// ═══════════════════════════════════════════════════════════════
describe('calcSubtotal — 合计行恒等 (CP-K11-05)', () => {
  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素数组', () => {
    expect(calcSubtotal([999])).toBe(999)
  })

  it('多元素求和', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
  })

  it('含负数', () => {
    expect(calcSubtotal([500, -200, 100])).toBe(400)
  })

  it('含零值', () => {
    expect(calcSubtotal([0, 0, 0])).toBe(0)
    expect(calcSubtotal([100, 0, 200])).toBe(300)
  })

  it('NaN元素处理（视为0）', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
    expect(calcSubtotal([NaN, NaN, NaN])).toBe(0)
  })

  it('大数组（模拟50行明细）', () => {
    const arr = Array.from({ length: 50 }, (_, i) => (i + 1) * 100)
    const expected = arr.reduce((s, x) => s + x, 0)
    expect(calcSubtotal(arr)).toBe(expected)
  })

  it('非数组输入防御', () => {
    // @ts-expect-error 测试非法输入
    expect(calcSubtotal(null)).toBe(0)
    // @ts-expect-error 测试非法输入
    expect(calcSubtotal(undefined)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════
// CP-K11-03: calcImpairmentSummary — 减值汇总=Σ各来源
// ═══════════════════════════════════════════════════════════════
describe('calcImpairmentSummary — 减值汇总=Σ各来源 (CP-K11-03)', () => {
  it('单一来源', () => {
    expect(calcImpairmentSummary([5000])).toBe(5000)
  })

  it('多来源汇总（F2+H1+I1+I3+在建+长投+其他）', () => {
    const sources = [1000, 2000, 500, 800, 300, 150, 250]
    expect(calcImpairmentSummary(sources)).toBe(5000)
  })

  it('空数组返回0', () => {
    expect(calcImpairmentSummary([])).toBe(0)
  })

  it('全零来源', () => {
    expect(calcImpairmentSummary([0, 0, 0, 0])).toBe(0)
  })

  it('含负数（转回场景）', () => {
    // 某些资产类别可能有转回导致负值
    expect(calcImpairmentSummary([1000, -200, 500])).toBe(1300)
  })

  it('NaN元素防御', () => {
    expect(calcImpairmentSummary([1000, NaN, 2000])).toBe(3000)
  })

  it('非数组输入防御', () => {
    // @ts-expect-error 测试非法输入
    expect(calcImpairmentSummary(null)).toBe(0)
    // @ts-expect-error 测试非法输入
    expect(calcImpairmentSummary(undefined)).toBe(0)
  })

  it('与calcSubtotal行为一致（两者逻辑相同）', () => {
    const sources = [100, 200, 300, 400, 500]
    expect(calcImpairmentSummary(sources)).toBe(calcSubtotal(sources))
  })
})
