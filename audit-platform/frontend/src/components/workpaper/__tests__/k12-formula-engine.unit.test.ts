/**
 * 单元测试 — K12 营业外收入公式引擎 useK12FormulaEngine
 *
 * 覆盖 5 个纯函数的确定性边界测试（非PBT），与 PBT 互补。
 * 科目：6301营业外收入（损益类/贷方科目，取发生额非余额）
 * 方向：收入类发生额 = 贷方发生 - 借方发生（贷方=收入增加）
 *
 * Spec: .kiro/specs/k12-non-operating-income/
 * Requirements: CP-K12-01~05
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
// parseNum 安全解析
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — parseNum', () => {
  it('null/undefined/空串→0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
  })

  it('NaN字符串/Infinity→0', () => {
    expect(parseNum('NaN')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('正常数字透传', () => {
    expect(parseNum(42)).toBe(42)
    expect(parseNum(-3.14)).toBe(-3.14)
    expect(parseNum('100.5')).toBe(100.5)
  })

  it('非数字字符串→0', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum('  ')).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-01: calcAuditedAmount 审定数=未审+AJE+RJE
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcAuditedAmount (CP-K12-01)', () => {
  it('正常计算: 100000+5000+(-2000)=103000', () => {
    expect(calcAuditedAmount(100000, 5000, -2000)).toBe(103000)
  })

  it('全零: 0+0+0=0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数: -50000+10000+(-3000)=-43000', () => {
    expect(calcAuditedAmount(-50000, 10000, -3000)).toBe(-43000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-02: calcIncomeStatementOccurrence 收入发生额=贷方-借方（贷方科目！）
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcIncomeStatementOccurrence (CP-K12-02)', () => {
  it('正常: 贷方80000-借方10000=70000（净收入）', () => {
    expect(calcIncomeStatementOccurrence(80000, 10000)).toBe(70000)
  })

  it('全贷方无红冲: 50000-0=50000', () => {
    expect(calcIncomeStatementOccurrence(50000, 0)).toBe(50000)
  })

  it('红冲超过贷方: 10000-30000=-20000（净冲减）', () => {
    expect(calcIncomeStatementOccurrence(10000, 30000)).toBe(-20000)
  })

  it('全零: 0-0=0', () => {
    expect(calcIncomeStatementOccurrence(0, 0)).toBe(0)
  })

  it('⚠️ 方向验证：与K8/K11(借方科目)相反', () => {
    // K12(贷方科目): credit - debit = 收入增加
    // K8/K11(借方科目): debit - credit = 费用/损失增加
    const credit = 100000
    const debit = 20000
    expect(calcIncomeStatementOccurrence(credit, debit)).toBe(80000) // credit - debit
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-03: calcYoYChange 同比变动率=(本期-上期)/上期
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcYoYChange (CP-K12-03)', () => {
  it('正常增长: (150000-100000)/100000=0.5', () => {
    expect(calcYoYChange(150000, 100000)).toBe(0.5)
  })

  it('减少: (60000-100000)/100000=-0.4', () => {
    expect(calcYoYChange(60000, 100000)).toBe(-0.4)
  })

  it('无变动: (100000-100000)/100000=0', () => {
    expect(calcYoYChange(100000, 100000)).toBe(0)
  })

  it('上期为0→null（除零保护）', () => {
    expect(calcYoYChange(50000, 0)).toBeNull()
  })

  it('两期都为0→null（上期为0）', () => {
    expect(calcYoYChange(0, 0)).toBeNull()
  })

  it('负上期: (50000-(-100000))/(-100000)=-1.5', () => {
    expect(calcYoYChange(50000, -100000)).toBe(-1.5)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-04: calcProportion 占比=单项/合计
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcProportion (CP-K12-04)', () => {
  it('正常: 25000/100000=0.25', () => {
    expect(calcProportion(25000, 100000)).toBe(0.25)
  })

  it('合计为0→null（除零保护）', () => {
    expect(calcProportion(10000, 0)).toBeNull()
  })

  it('单项为0: 0/100000=0', () => {
    expect(calcProportion(0, 100000)).toBe(0)
  })

  it('单项等于合计: 100000/100000=1', () => {
    expect(calcProportion(100000, 100000)).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CP-K12-05: calcSubtotal 合计行恒等=Σarr
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK12FormulaEngine — calcSubtotal (CP-K12-05)', () => {
  it('空数组=0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('正常求和: [10000,20000,30000]=60000', () => {
    expect(calcSubtotal([10000, 20000, 30000])).toBe(60000)
  })

  it('含负数: [50000,-10000,30000]=70000', () => {
    expect(calcSubtotal([50000, -10000, 30000])).toBe(70000)
  })

  it('单元素: [42000]=42000', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('非数组防御: 返回0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})
