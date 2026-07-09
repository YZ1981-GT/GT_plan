/**
 * K10 其他收益 — 单元测试：useK10FormulaEngine + useK10GrantReconcileEngine
 *
 * Spec: .kiro/specs/k10-other-income/ Task 7.1
 * Validates: CP-K10-01~06
 *
 * 确定性单元测试（非PBT），覆盖：
 * 1. calcAuditedAmount: 审定数=未审+AJE+RJE
 * 2. calcIncomeStatementOccurrence: 收益类发生额=贷方-借方
 * 3. calcYoYChange: 同比变动率
 * 4. calcSubtotal: 合计行
 * 5. calcTotalRecognized: 合计计入=直接+递延
 * 6. isConsistentWithK7: K7一致性判断
 * 7. parseNum: 安全数字解析
 */
import { describe, it, expect } from 'vitest'

import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcYoYChange,
  calcSubtotal,
} from '../useK10FormulaEngine'

import {
  calcTotalRecognized,
  isConsistentWithK7,
} from '../useK10GrantReconcileEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. calcAuditedAmount: 审定数=未审+AJE+RJE (CP-K10-01)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAuditedAmount (CP-K10-01)', () => {
  it('基本计算: 100 + 20 + 10 = 130', () => {
    expect(calcAuditedAmount(100, 20, 10)).toBe(130)
  })

  it('全部为0: 0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数AJE: 500 + (-30) + 0 = 470', () => {
    expect(calcAuditedAmount(500, -30, 0)).toBe(470)
  })

  it('负数RJE: 1000 + 0 + (-200) = 800', () => {
    expect(calcAuditedAmount(1000, 0, -200)).toBe(800)
  })

  it('全部负数: -100 + (-50) + (-25) = -175', () => {
    expect(calcAuditedAmount(-100, -50, -25)).toBe(-175)
  })

  it('大数值: 999999999 + 1 + 0 = 1000000000', () => {
    expect(calcAuditedAmount(999999999, 1, 0)).toBe(1000000000)
  })

  it('小数精度: 100.55 + 20.33 + 10.12 = 131.00', () => {
    expect(calcAuditedAmount(100.55, 20.33, 10.12)).toBeCloseTo(131.0, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. calcIncomeStatementOccurrence: 收益类发生额=贷方-借方 (CP-K10-02)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcIncomeStatementOccurrence (CP-K10-02)', () => {
  it('贷方>借方（正常收益净增加）: 50000 - 8000 = 42000', () => {
    expect(calcIncomeStatementOccurrence(50000, 8000)).toBe(42000)
  })

  it('贷方<借方（收益净冲回/红冲）: 3000 - 5000 = -2000', () => {
    expect(calcIncomeStatementOccurrence(3000, 5000)).toBe(-2000)
  })

  it('贷方=借方（净额为零）: 10000 - 10000 = 0', () => {
    expect(calcIncomeStatementOccurrence(10000, 10000)).toBe(0)
  })

  it('只有贷方（无红冲）: 25000 - 0 = 25000', () => {
    expect(calcIncomeStatementOccurrence(25000, 0)).toBe(25000)
  })

  it('只有借方（全额冲回）: 0 - 15000 = -15000', () => {
    expect(calcIncomeStatementOccurrence(0, 15000)).toBe(-15000)
  })

  it('全部为0: 0 - 0 = 0', () => {
    expect(calcIncomeStatementOccurrence(0, 0)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. calcYoYChange: 同比变动率 (CP-K10-05)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcYoYChange (CP-K10-05)', () => {
  it('正增长: (120000 - 100000) / 100000 = 0.2', () => {
    expect(calcYoYChange(120000, 100000)).toBeCloseTo(0.2, 10)
  })

  it('负增长（下降）: (80000 - 100000) / 100000 = -0.2', () => {
    expect(calcYoYChange(80000, 100000)).toBeCloseTo(-0.2, 10)
  })

  it('上期为0返回null（除零保护）', () => {
    expect(calcYoYChange(50000, 0)).toBeNull()
  })

  it('本期为0 + 上期≠0: (0 - 100000) / 100000 = -1', () => {
    expect(calcYoYChange(0, 100000)).toBeCloseTo(-1, 10)
  })

  it('翻倍增长: (200000 - 100000) / 100000 = 1.0', () => {
    expect(calcYoYChange(200000, 100000)).toBeCloseTo(1.0, 10)
  })

  it('无变化: (100000 - 100000) / 100000 = 0', () => {
    expect(calcYoYChange(100000, 100000)).toBe(0)
  })

  it('负数场景: (-50 - (-100)) / (-100) = -0.5', () => {
    expect(calcYoYChange(-50, -100)).toBeCloseTo(-0.5, 10)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. calcSubtotal: 合计行 (CP-K10-06)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcSubtotal (CP-K10-06)', () => {
  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素: [42000] = 42000', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('多元素: [10000, 20000, 5000, 7000] = 42000', () => {
    expect(calcSubtotal([10000, 20000, 5000, 7000])).toBe(42000)
  })

  it('包含负数: [30000, -5000, 10000] = 35000', () => {
    expect(calcSubtotal([30000, -5000, 10000])).toBe(35000)
  })

  it('NaN处理: NaN视为0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('全部为0: [0, 0, 0] = 0', () => {
    expect(calcSubtotal([0, 0, 0])).toBe(0)
  })

  it('大数组求和', () => {
    const arr = Array.from({ length: 100 }, (_, i) => i + 1)
    expect(calcSubtotal(arr)).toBe(5050)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. calcTotalRecognized: 合计计入=直接+递延 (CP-K10-03)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcTotalRecognized (CP-K10-03)', () => {
  it('基本求和: 15000 + 8000 = 23000', () => {
    expect(calcTotalRecognized(15000, 8000)).toBe(23000)
  })

  it('直接为0: 0 + 12000 = 12000', () => {
    expect(calcTotalRecognized(0, 12000)).toBe(12000)
  })

  it('递延为0: 20000 + 0 = 20000', () => {
    expect(calcTotalRecognized(20000, 0)).toBe(20000)
  })

  it('两者都为0: 0 + 0 = 0', () => {
    expect(calcTotalRecognized(0, 0)).toBe(0)
  })

  it('含小数: 15000.5 + 8000.3 = 23000.8', () => {
    expect(calcTotalRecognized(15000.5, 8000.3)).toBeCloseTo(23000.8, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6. isConsistentWithK7: K7一致性判断 (CP-K10-04)
// ═══════════════════════════════════════════════════════════════════════════════

describe('isConsistentWithK7 (CP-K10-04)', () => {
  it('完全匹配（差额=0）→ true', () => {
    expect(isConsistentWithK7(8000, 8000)).toBe(true)
  })

  it('差额=0.005（<0.01）→ true', () => {
    expect(isConsistentWithK7(8000.005, 8000)).toBe(true)
  })

  it('差额=0.009（<0.01）→ true', () => {
    expect(isConsistentWithK7(8000, 8000.009)).toBe(true)
  })

  it('差额=0.01（>=0.01）→ false', () => {
    expect(isConsistentWithK7(8000.01, 8000)).toBe(false)
  })

  it('差额=100（远超容差）→ false', () => {
    expect(isConsistentWithK7(8100, 8000)).toBe(false)
  })

  it('负方向差额=-0.005 → true', () => {
    expect(isConsistentWithK7(7999.995, 8000)).toBe(true)
  })

  it('两者都为0 → true', () => {
    expect(isConsistentWithK7(0, 0)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7. parseNum: 安全数字解析
// ═══════════════════════════════════════════════════════════════════════════════

describe('parseNum', () => {
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

  it('"123" → 123', () => {
    expect(parseNum('123')).toBe(123)
  })

  it('"" → 0', () => {
    expect(parseNum('')).toBe(0)
  })

  it('"  " → 0', () => {
    expect(parseNum('  ')).toBe(0)
  })

  it('"NaN" → 0', () => {
    expect(parseNum('NaN')).toBe(0)
  })

  it('正常数字直接返回: 42.5 → 42.5', () => {
    expect(parseNum(42.5)).toBe(42.5)
  })

  it('0 → 0', () => {
    expect(parseNum(0)).toBe(0)
  })

  it('负数: -100 → -100', () => {
    expect(parseNum(-100)).toBe(-100)
  })

  it('"3.14" → 3.14', () => {
    expect(parseNum('3.14')).toBeCloseTo(3.14, 10)
  })
})
