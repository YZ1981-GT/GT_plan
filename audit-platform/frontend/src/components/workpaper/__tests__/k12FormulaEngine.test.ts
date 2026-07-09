/**
 * 单元测试 — K12 营业外收入公式引擎 useK12FormulaEngine
 *
 * 全面覆盖 5 个纯函数的确定性边界测试（损益方向+同比/占比+边界）。
 * 科目：6301 营业外收入（损益类/贷方科目，取发生额非余额）
 * 方向：收入类发生额 = 贷方发生 - 借方发生（贷方=收入增加）
 *
 * Spec: .kiro/specs/k12-non-operating-income/ Task 7.1
 * Validates: Requirements CP-K12-01~05
 */

import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcYoYChange,
  calcProportion,
  calcSubtotal,
} from '../composables/useK12FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// parseNum 安全数字解析
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — parseNum 安全解析', () => {
  it('null → 0', () => expect(parseNum(null)).toBe(0))
  it('undefined → 0', () => expect(parseNum(undefined)).toBe(0))
  it('空串 → 0', () => expect(parseNum('')).toBe(0))
  it('NaN → 0', () => expect(parseNum(NaN)).toBe(0))
  it('"NaN" 字符串 → 0', () => expect(parseNum('NaN')).toBe(0))
  it('Infinity → 0', () => expect(parseNum(Infinity)).toBe(0))
  it('-Infinity → 0', () => expect(parseNum(-Infinity)).toBe(0))
  it('非数字字符串 "abc" → 0', () => expect(parseNum('abc')).toBe(0))
  it('空白字符串 → 0', () => expect(parseNum('   ')).toBe(0))
  it('正常数字透传: 42', () => expect(parseNum(42)).toBe(42))
  it('负数透传: -3.14', () => expect(parseNum(-3.14)).toBe(-3.14))
  it('字符串数字解析: "100.5"', () => expect(parseNum('100.5')).toBe(100.5))
  it('大数值透传: 1e15', () => expect(parseNum(1e15)).toBe(1e15))
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-01: calcAuditedAmount 审定数 = 未审数 + AJE + RJE
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcAuditedAmount (CP-K12-01)', () => {
  it('正常三项相加: 100000 + 5000 + (-2000) = 103000', () => {
    expect(calcAuditedAmount(100000, 5000, -2000)).toBe(103000)
  })

  it('全零: 0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('全负数: -50000 + (-10000) + (-3000) = -63000', () => {
    expect(calcAuditedAmount(-50000, -10000, -3000)).toBe(-63000)
  })

  it('未审为负(冲回场景): -20000 + 30000 + 5000 = 15000', () => {
    expect(calcAuditedAmount(-20000, 30000, 5000)).toBe(15000)
  })

  it('大数值精度: 1e12 + 1e12 + 1e12 = 3e12', () => {
    expect(calcAuditedAmount(1e12, 1e12, 1e12)).toBe(3e12)
  })

  it('小数精度: 0.1 + 0.2 + 0 近似 0.3', () => {
    expect(calcAuditedAmount(0.1, 0.2, 0)).toBeCloseTo(0.3, 10)
  })

  it('仅AJE有值: 0 + 100000 + 0 = 100000', () => {
    expect(calcAuditedAmount(0, 100000, 0)).toBe(100000)
  })

  it('仅RJE有值: 0 + 0 + (-50000) = -50000', () => {
    expect(calcAuditedAmount(0, 0, -50000)).toBe(-50000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-02: calcIncomeStatementOccurrence 损益类收入发生额 = 贷方 - 借方
// 6301 是贷方科目: 贷方=收入增加, 借方=红冲/结转
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcIncomeStatementOccurrence (CP-K12-02)', () => {
  it('正常: 贷方80000 - 借方10000 = 70000（净收入增加）', () => {
    expect(calcIncomeStatementOccurrence(80000, 10000)).toBe(70000)
  })

  it('纯贷方无红冲: 50000 - 0 = 50000', () => {
    expect(calcIncomeStatementOccurrence(50000, 0)).toBe(50000)
  })

  it('红冲超过贷方（净冲减）: 10000 - 30000 = -20000', () => {
    expect(calcIncomeStatementOccurrence(10000, 30000)).toBe(-20000)
  })

  it('全零: 0 - 0 = 0', () => {
    expect(calcIncomeStatementOccurrence(0, 0)).toBe(0)
  })

  it('借贷相等: 50000 - 50000 = 0', () => {
    expect(calcIncomeStatementOccurrence(50000, 50000)).toBe(0)
  })

  it('⚠️ 方向验证: K12贷方科目 credit-debit (与K8/K11借方科目相反)', () => {
    // 6301营业外收入: credit - debit → 正值表示收入净增加
    const credit = 200000
    const debit = 50000
    const result = calcIncomeStatementOccurrence(credit, debit)
    expect(result).toBe(150000)
    // 正值=净收入, 符合贷方科目性质
    expect(result).toBeGreaterThan(0)
  })

  it('大数值: 1e12 - 500000000000 = 500000000000', () => {
    expect(calcIncomeStatementOccurrence(1e12, 5e11)).toBe(5e11)
  })

  it('负输入(异常数据防御): parseNum兜底', () => {
    // 实际业务中贷方/借方应≥0, 但函数不限制
    expect(calcIncomeStatementOccurrence(-10000, -5000)).toBe(-5000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-03: calcYoYChange 同比变动率 = (本期 - 上期) / 上期
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcYoYChange (CP-K12-03)', () => {
  it('正增长50%: (150000 - 100000) / 100000 = 0.5', () => {
    expect(calcYoYChange(150000, 100000)).toBe(0.5)
  })

  it('下降40%: (60000 - 100000) / 100000 = -0.4', () => {
    expect(calcYoYChange(60000, 100000)).toBe(-0.4)
  })

  it('无变动: (100000 - 100000) / 100000 = 0', () => {
    expect(calcYoYChange(100000, 100000)).toBe(0)
  })

  it('上期为0 → null（除零保护）', () => {
    expect(calcYoYChange(50000, 0)).toBeNull()
  })

  it('两期都为0 → null', () => {
    expect(calcYoYChange(0, 0)).toBeNull()
  })

  it('本期为0上期非零: (0 - 80000) / 80000 = -1', () => {
    expect(calcYoYChange(0, 80000)).toBe(-1)
  })

  it('负上期: (50000 - (-100000)) / (-100000) = -1.5', () => {
    expect(calcYoYChange(50000, -100000)).toBe(-1.5)
  })

  it('两期均为负: (-30000 - (-50000)) / (-50000) = -0.4', () => {
    expect(calcYoYChange(-30000, -50000)).toBeCloseTo(-0.4, 10)
  })

  it('大数值: (2e12 - 1e12) / 1e12 = 1', () => {
    expect(calcYoYChange(2e12, 1e12)).toBe(1)
  })

  it('极小上期: (100 - 0.01) / 0.01 ≈ 9999', () => {
    expect(calcYoYChange(100, 0.01)).toBeCloseTo(9999, 5)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-04: calcProportion 占比 = 单项 / 合计
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcProportion (CP-K12-04)', () => {
  it('正常: 25000 / 100000 = 0.25', () => {
    expect(calcProportion(25000, 100000)).toBe(0.25)
  })

  it('合计为0 → null（除零保护）', () => {
    expect(calcProportion(10000, 0)).toBeNull()
  })

  it('单项为0: 0 / 100000 = 0', () => {
    expect(calcProportion(0, 100000)).toBe(0)
  })

  it('单项等于合计: 100000 / 100000 = 1', () => {
    expect(calcProportion(100000, 100000)).toBe(1)
  })

  it('单项大于合计(异常情况): 150000 / 100000 = 1.5', () => {
    expect(calcProportion(150000, 100000)).toBe(1.5)
  })

  it('负单项: -20000 / 100000 = -0.2', () => {
    expect(calcProportion(-20000, 100000)).toBe(-0.2)
  })

  it('负合计: 50000 / (-200000) = -0.25', () => {
    expect(calcProportion(50000, -200000)).toBe(-0.25)
  })

  it('极小比例: 1 / 1e12', () => {
    expect(calcProportion(1, 1e12)).toBeCloseTo(1e-12, 15)
  })

  it('两者都为0 → null', () => {
    expect(calcProportion(0, 0)).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-05: calcSubtotal 合计行 = Σ(数组)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcSubtotal (CP-K12-05)', () => {
  it('空数组 = 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('正常求和: [10000, 20000, 30000] = 60000', () => {
    expect(calcSubtotal([10000, 20000, 30000])).toBe(60000)
  })

  it('含负数: [50000, -10000, 30000] = 70000', () => {
    expect(calcSubtotal([50000, -10000, 30000])).toBe(70000)
  })

  it('单元素: [42000] = 42000', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('全零数组: [0, 0, 0, 0] = 0', () => {
    expect(calcSubtotal([0, 0, 0, 0])).toBe(0)
  })

  it('全负数: [-100, -200, -300] = -600', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('大数组精度(模拟审定表多行): 20项求和', () => {
    const arr = Array.from({ length: 20 }, (_, i) => (i + 1) * 10000)
    // 10000+20000+...+200000 = 10000*(1+2+...+20) = 10000*210 = 2100000
    expect(calcSubtotal(arr)).toBe(2100000)
  })

  it('大数值精度: [1e12, 2e12, 3e12] = 6e12', () => {
    expect(calcSubtotal([1e12, 2e12, 3e12])).toBe(6e12)
  })

  it('非数组防御: null → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
  })

  it('非数组防御: undefined → 0', () => {
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})
