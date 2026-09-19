/**
 * I6 研发费用 — useI6FormulaEngine 单元测试（确定性）
 *
 * 损益类公式引擎纯函数验证。
 * PBT测试在 useI6FormulaEngine.pbt.test.ts 中覆盖随机输入。
 * 本文件覆盖具体边界值和业务场景。
 *
 * Spec: .kiro/specs/i6-research-development-expense/ Task 7.1
 * Validates: Requirements 2.2-2.6, 4.4, 10.1-10.3
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementNet,
  calcSubtotal,
  calcMonthlyTotal,
  calcChangeRate,
  calcResearchTotal,
  validateVRI601,
  calcDebitCreditBalance,
  isCutoffCrossover,
} from '../composables/useI6FormulaEngine'

// ─── parseNum 安全数字解析 ─────────────────────────────────────────────────

describe('useI6FormulaEngine — parseNum', () => {
  it('parseNum(null) === 0', () => {
    expect(parseNum(null)).toBe(0)
  })

  it('parseNum(NaN) === 0', () => {
    expect(parseNum(NaN)).toBe(0)
  })

  it('parseNum("abc") === 0', () => {
    expect(parseNum('abc')).toBe(0)
  })

  it('parseNum(undefined) === 0', () => {
    expect(parseNum(undefined)).toBe(0)
  })

  it('parseNum("") === 0', () => {
    expect(parseNum('')).toBe(0)
  })

  it('parseNum("123.45") === 123.45', () => {
    expect(parseNum('123.45')).toBe(123.45)
  })

  it('parseNum(Infinity) === 0', () => {
    expect(parseNum(Infinity)).toBe(0)
  })
})

// ─── calcAuditedAmount 审定数=未审+AJE+RJE ────────────────────────────────

describe('useI6FormulaEngine — calcAuditedAmount', () => {
  it('calcAuditedAmount(100, 20, -5) === 115', () => {
    expect(calcAuditedAmount(100, 20, -5)).toBe(115)
  })

  it('全零输入返回0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数场景正确计算', () => {
    expect(calcAuditedAmount(-100, 50, 30)).toBe(-20)
  })
})

// ─── calcIncomeStatementNet 损益类净发生额=借方-贷方 ───────────────────────

describe('useI6FormulaEngine — calcIncomeStatementNet', () => {
  it('calcIncomeStatementNet(50000, 10000) === 40000', () => {
    expect(calcIncomeStatementNet(50000, 10000)).toBe(40000)
  })

  it('贷方大于借方返回负数（费用冲回）', () => {
    expect(calcIncomeStatementNet(10000, 50000)).toBe(-40000)
  })

  it('借贷相等返回0', () => {
    expect(calcIncomeStatementNet(30000, 30000)).toBe(0)
  })
})

// ─── calcSubtotal 合计 ──────────────────────────────────────────────────────

describe('useI6FormulaEngine — calcSubtotal', () => {
  it('calcSubtotal([]) === 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素数组', () => {
    expect(calcSubtotal([100])).toBe(100)
  })

  it('多元素求和', () => {
    expect(calcSubtotal([10, 20, 30])).toBe(60)
  })

  it('包含负数', () => {
    expect(calcSubtotal([100, -20, 50])).toBe(130)
  })
})

// ─── calcMonthlyTotal 月度合计=SUM(1月~12月) ──────────────────────────────

describe('useI6FormulaEngine — calcMonthlyTotal', () => {
  it('calcMonthlyTotal([1,2,3,4,5,6,7,8,9,10,11,12]) === 78', () => {
    expect(calcMonthlyTotal([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])).toBe(78)
  })

  it('空数组返回0', () => {
    expect(calcMonthlyTotal([])).toBe(0)
  })

  it('全零返回0', () => {
    expect(calcMonthlyTotal([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])).toBe(0)
  })
})

// ─── calcChangeRate 变动率=(本期-同期)/同期×100% ──────────────────────────

describe('useI6FormulaEngine — calcChangeRate', () => {
  it('calcChangeRate(120, 100) === 20', () => {
    expect(calcChangeRate(120, 100)).toBe(20)
  })

  it('calcChangeRate(50, 0) === null', () => {
    expect(calcChangeRate(50, 0)).toBeNull()
  })

  it('下降场景返回负数', () => {
    expect(calcChangeRate(80, 100)).toBe(-20)
  })

  it('无变化返回0', () => {
    expect(calcChangeRate(100, 100)).toBe(0)
  })
})

// ─── calcResearchTotal 研发总额=费用化+资本化 ───────────────────────────────

describe('useI6FormulaEngine — calcResearchTotal', () => {
  it('calcResearchTotal(200000, 100000) === 300000', () => {
    expect(calcResearchTotal(200000, 100000)).toBe(300000)
  })

  it('资本化为0时等于费用化', () => {
    expect(calcResearchTotal(150000, 0)).toBe(150000)
  })
})

// ─── validateVRI601 VR-I6-01校验 ──────────────────────────────────────────

describe('useI6FormulaEngine — validateVRI601', () => {
  it('validateVRI601(200000, 100000, 300000).isValid === true', () => {
    const result = validateVRI601(200000, 100000, 300000)
    expect(result.isValid).toBe(true)
    expect(result.difference).toBeCloseTo(0, 2)
  })

  it('validateVRI601(200000, 100000, 250000).isValid === false', () => {
    const result = validateVRI601(200000, 100000, 250000)
    expect(result.isValid).toBe(false)
    expect(result.difference).toBe(50000)
  })

  it('微小差异(<0.01)视为平衡', () => {
    const result = validateVRI601(200000, 100000, 300000.005)
    expect(result.isValid).toBe(true)
  })
})

// ─── calcDebitCreditBalance 借贷平衡 ────────────────────────────────────────

describe('useI6FormulaEngine — calcDebitCreditBalance', () => {
  it('calcDebitCreditBalance([100,200], [100,200]).isBalanced === true', () => {
    const result = calcDebitCreditBalance([100, 200], [100, 200])
    expect(result.isBalanced).toBe(true)
    expect(result.totalDebit).toBe(300)
    expect(result.totalCredit).toBe(300)
  })

  it('不平衡场景', () => {
    const result = calcDebitCreditBalance([100, 200], [50, 100])
    expect(result.isBalanced).toBe(false)
    expect(result.totalDebit).toBe(300)
    expect(result.totalCredit).toBe(150)
  })

  it('空数组平衡(0===0)', () => {
    const result = calcDebitCreditBalance([], [])
    expect(result.isBalanced).toBe(true)
    expect(result.totalDebit).toBe(0)
    expect(result.totalCredit).toBe(0)
  })
})

// ─── isCutoffCrossover 截止测试日期差判断 ────────────────────────────────────

describe('useI6FormulaEngine — isCutoffCrossover', () => {
  it('isCutoffCrossover(2024-12-28, 2025-01-05, 5) === true (差8天>5天)', () => {
    const result = isCutoffCrossover(new Date('2024-12-28'), new Date('2025-01-05'), 5)
    expect(result).toBe(true)
  })

  it('isCutoffCrossover(2024-12-30, 2025-01-02, 5) === false (差3天≤5天)', () => {
    const result = isCutoffCrossover(new Date('2024-12-30'), new Date('2025-01-02'), 5)
    expect(result).toBe(false)
  })

  it('相同日期不跨期(差0天)', () => {
    const result = isCutoffCrossover(new Date('2024-12-31'), new Date('2024-12-31'), 5)
    expect(result).toBe(false)
  })

  it('恰好等于阈值不跨期(差=5天)', () => {
    const result = isCutoffCrossover(new Date('2024-12-26'), new Date('2024-12-31'), 5)
    expect(result).toBe(false)
  })

  it('无效日期返回false', () => {
    expect(isCutoffCrossover(new Date('invalid'), new Date('2024-12-31'), 5)).toBe(false)
  })
})
