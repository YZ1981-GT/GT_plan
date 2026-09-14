/**
 * Unit Tests — J1 useJ1FormulaEngine + useJ1SalaryCalc
 *
 * 覆盖：负债类公式、审定数、月度、分配闭合、薪酬测算
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Task: 7.1
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcChangeDiff,
  calcChangeRate,
  calcSubtotal,
  calcProportion,
  calcMonthlyTotal,
  calcMonthlyAverage,
  validateAllocationClosure,
} from '../useJ1FormulaEngine'
import {
  calcSalaryEstimate,
  calcInsuranceEstimate,
  calcHousingFundEstimate,
  calcAccrualDiffRate,
  calcPerCapitaSalary,
  calcSalaryRevenueRatio,
  calcIndustryDiffRate,
} from '../useJ1SalaryCalc'

// ─── parseNum ─────────────────────────────────────────────────────────────────
describe('parseNum', () => {
  it('null/undefined/empty → 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
  })
  it('NaN/Infinity → 0', () => {
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
  })
  it('正常数字', () => {
    expect(parseNum(42)).toBe(42)
    expect(parseNum('3.14')).toBeCloseTo(3.14)
  })
})

// ─── calcAuditedAmount ───────────────────────────────────────────────────────
describe('calcAuditedAmount', () => {
  it('审定=未审+AJE+RJE', () => {
    expect(calcAuditedAmount(1000, 50, -30)).toBe(1020)
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })
})

// ─── calcLiabilityEndBalance ─────────────────────────────────────────────────
describe('calcLiabilityEndBalance', () => {
  it('负债类期末=期初+贷方-借方', () => {
    expect(calcLiabilityEndBalance(100, 50, 30)).toBe(120)
    expect(calcLiabilityEndBalance(0, 100, 0)).toBe(100)
    expect(calcLiabilityEndBalance(100, 0, 100)).toBe(0)
  })
})

// ─── calcChangeDiff ──────────────────────────────────────────────────────────
describe('calcChangeDiff', () => {
  it('变动额=本期-上期', () => {
    expect(calcChangeDiff(150, 100)).toBe(50)
    expect(calcChangeDiff(80, 100)).toBe(-20)
  })
})

// ─── calcChangeRate ──────────────────────────────────────────────────────────
describe('calcChangeRate', () => {
  it('正常计算', () => {
    expect(calcChangeRate(150, 100)).toBeCloseTo(50, 5)
    expect(calcChangeRate(80, 100)).toBeCloseTo(-20, 5)
  })
  it('基数=0边界', () => {
    expect(calcChangeRate(0, 0)).toBe(0)
    expect(calcChangeRate(100, 0)).toBe(100)
  })
})

// ─── calcSubtotal ────────────────────────────────────────────────────────────
describe('calcSubtotal', () => {
  it('合计=SUM', () => {
    expect(calcSubtotal([1, 2, 3])).toBe(6)
    expect(calcSubtotal([])).toBe(0)
  })
})

// ─── calcProportion ──────────────────────────────────────────────────────────
describe('calcProportion', () => {
  it('正常占比', () => { expect(calcProportion(25, 100)).toBe(0.25) })
  it('分母=0', () => { expect(calcProportion(25, 0)).toBe(0) })
})

// ─── calcMonthlyTotal / Average ──────────────────────────────────────────────
describe('calcMonthlyTotal & Average', () => {
  const months = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
  it('合计=SUM(12月)', () => { expect(calcMonthlyTotal(months)).toBe(780) })
  it('均值=合计/12', () => { expect(calcMonthlyAverage(months)).toBe(65) })
  it('空数组→0', () => { expect(calcMonthlyAverage([])).toBe(0) })
})

// ─── validateAllocationClosure ──────────────────────────────────────────────
describe('validateAllocationClosure', () => {
  it('闭合情况', () => {
    const r = validateAllocationClosure([100, 200, 300], 600)
    expect(r.isValid).toBe(true)
    expect(r.difference).toBeCloseTo(0)
  })
  it('不闭合情况', () => {
    const r = validateAllocationClosure([100, 200, 300], 700)
    expect(r.isValid).toBe(false)
    expect(r.difference).toBeCloseTo(-100)
  })
})

// ─── Salary Calc ─────────────────────────────────────────────────────────────
describe('calcSalaryEstimate', () => {
  it('100人×5000元×12月=600万', () => {
    expect(calcSalaryEstimate(100, 5000, 12)).toBe(6000000)
  })
})

describe('calcInsuranceEstimate', () => {
  it('基数10000×比例0.16×12月=19200', () => {
    expect(calcInsuranceEstimate(10000, 0.16, 12)).toBeCloseTo(19200)
  })
})

describe('calcHousingFundEstimate', () => {
  it('基数10000×比例0.12×12月=14400', () => {
    expect(calcHousingFundEstimate(10000, 0.12, 12)).toBeCloseTo(14400)
  })
})

describe('calcAccrualDiffRate', () => {
  it('正常差异率', () => {
    expect(calcAccrualDiffRate(105, 100)).toBeCloseTo(5)
  })
  it('估算为0时返回null', () => {
    expect(calcAccrualDiffRate(100, 0)).toBeNull()
  })
})

describe('calcPerCapitaSalary', () => {
  it('正常计算', () => { expect(calcPerCapitaSalary(600000, 100)).toBe(6000) })
  it('人数=0', () => { expect(calcPerCapitaSalary(600000, 0)).toBeNull() })
})

describe('calcSalaryRevenueRatio', () => {
  it('薪酬占比', () => { expect(calcSalaryRevenueRatio(100000, 1000000)).toBeCloseTo(10) })
  it('收入=0', () => { expect(calcSalaryRevenueRatio(100000, 0)).toBeNull() })
})

describe('calcIndustryDiffRate', () => {
  it('正常差异率', () => { expect(calcIndustryDiffRate(120, 100)).toBeCloseTo(20) })
  it('行业均值=0', () => { expect(calcIndustryDiffRate(120, 0)).toBeNull() })
})
